using System.Security.Cryptography;
using System.Text.Json;

namespace FileGuard.Recovery;

public sealed record RecoveryOptions
{
    public required string ProtectedRoot { get; init; }
    public required string RepositoryRoot { get; init; }
    public required string StateRoot { get; init; }
    public bool AutoRestore { get; init; }
    public int ScanSeconds { get; init; } = 2;
    public int SettleMilliseconds { get; init; } = 500;
    public long MaxFileBytes { get; init; } = 100 * 1024 * 1024;
    public int MaxRestoresPerMinute { get; init; } = 3;
    public string? ServerUrl { get; init; }
    public string? EnrollmentToken { get; init; }
    // A separate identity lets recovery coexist with the existing monitoring agent.
    public string Hostname { get; init; } = Environment.MachineName + "-RECOVERY";
    public bool AllowInsecureLoopback { get; init; }
}

public sealed record FileVersion(string Id, string Sha256, long Bytes, DateTime ModifiedUtc, DateTime CapturedUtc);
public sealed class FileHistory
{
    public List<FileVersion> Versions { get; set; } = [];
    public List<DateTime> Restores { get; set; } = [];
    public bool MissingReported { get; set; }
    public string? ProtectionSuspended { get; set; }
}
public sealed record RecoveryEvent(string EventId, string Ts, string Kind, string RelativePath,
    string? VersionId, string? Sha256, long? Bytes, string Message);

/// <summary>Lab content recovery. Never claims pre-delete blocking or complete NTFS metadata recovery.</summary>
public sealed class RecoveryEngine : IDisposable
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    private readonly RecoveryOptions options;
    private readonly string root, repository, state, manifest;
    private readonly FileStream instanceLock;
    private readonly Dictionary<string, FileHistory> histories;
    public IReadOnlyDictionary<string, FileHistory> Histories => histories;
    public string Status { get; private set; } = "starting";
    public string StatusMessage { get; private set; } = "Waiting for the first complete scan.";
    private static StringComparison Comparison => OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;

    public RecoveryEngine(RecoveryOptions options)
    {
        this.options = options;
        if (options.ScanSeconds < 1 || options.SettleMilliseconds < 0 || options.MaxFileBytes < 1 || options.MaxRestoresPerMinute < 1)
            throw new ArgumentException("Invalid recovery limits.");
        root = Normalize(options.ProtectedRoot); repository = Normalize(options.RepositoryRoot); state = Normalize(options.StateRoot);
        if (root == Path.GetPathRoot(root) || Within(root, repository) || Within(repository, root) || Within(root, state) || Within(state, root)
            || Within(state, repository) || Within(repository, state))
            throw new ArgumentException("Use three separate directories; never protect a volume root or put state/backups inside protected data.");
        foreach (string dir in new[] { root, repository, state })
        {
            RejectLinks(dir);
            if (!Directory.Exists(dir)) throw new DirectoryNotFoundException("Prepare the lab directories explicitly before starting the agent: " + dir);
        }
        instanceLock = new(Path.Combine(state, "instance.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        manifest = Path.Combine(state, "manifest.json");
        try
        {
            var loaded = File.Exists(manifest)
                ? JsonSerializer.Deserialize<Dictionary<string, FileHistory>>(File.ReadAllText(manifest), Json) ?? throw new InvalidDataException("Empty recovery manifest")
                : new Dictionary<string, FileHistory>();
            histories = new(loaded, OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);
            foreach (var entry in histories)
            {
                SafePath(entry.Key);
                if (entry.Value.Versions.Count == 0 || entry.Value.Versions.Any(v => !ValidHash(v.Sha256))) throw new InvalidDataException("Invalid recovery manifest");
            }
            Directory.CreateDirectory(Path.Combine(repository, "objects"));
            Directory.CreateDirectory(Path.Combine(state, "outbox"));
            RejectLinks(Path.Combine(repository, "objects")); RejectLinks(Path.Combine(state, "outbox"));
        }
        catch { instanceLock.Dispose(); throw; }
    }

    private static string Normalize(string path)
    {
        if (!Path.IsPathFullyQualified(path)) throw new ArgumentException("Recovery directories must use absolute paths.");
        return Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));
    }
    private static bool Within(string parent, string path) => path.Equals(parent, Comparison) || path.StartsWith(parent + Path.DirectorySeparatorChar, Comparison);
    public static bool ValidHash(string value) => value.Length == 64 && value.All(Uri.IsHexDigit);
    private static void RejectLinks(string path)
    {
        for (string? current = path; current is not null; current = Path.GetDirectoryName(current))
        {
            try
            {
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) throw new IOException("Symbolic links/reparse points are outside the recovery scope: " + current);
            }
            catch (FileNotFoundException) { }
            catch (DirectoryNotFoundException) { }
        }
    }
    private string SafePath(string relative)
    {
        if (relative.Length > 400 || Path.IsPathRooted(relative) || relative.Split('/', '\\').Any(p => p is ".." or "." or "") || relative.Contains(':'))
            throw new InvalidDataException("Invalid relative recovery path.");
        var path = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!Within(root, path) || path.Equals(root, Comparison)) throw new InvalidDataException("Recovery path escapes its configured root.");
        RejectLinks(path);
        return path;
    }
    private string Blob(FileVersion version)
    {
        if (!ValidHash(version.Sha256)) throw new InvalidDataException("Invalid object hash");
        string path = Path.Combine(repository, "objects", version.Sha256.ToLowerInvariant() + ".blob");
        RejectLinks(path);
        return path;
    }
    private static bool Excluded(string relative) => relative.Split('/', '\\').Any(p => p.StartsWith(".fileguard-", StringComparison.Ordinal))
        || new[] { ".tmp", ".temp", ".db", ".db-wal", ".db-shm", ".mdf", ".ldf" }.Any(ext => relative.EndsWith(ext, StringComparison.OrdinalIgnoreCase));

    public static void AtomicJson<T>(string path, T value)
    {
        RejectLinks(path);
        var temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var output = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { JsonSerializer.Serialize(output, value, Json); output.Flush(true); }
            File.Move(temp, path, true);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
    private void Save() => AtomicJson(manifest, histories);
    private void Emit(string kind, string relative, FileVersion? version, string message)
    {
        var item = new RecoveryEvent(Guid.NewGuid().ToString("N"), DateTime.UtcNow.ToString("O"), kind, relative,
            version?.Id, version?.Sha256, version?.Bytes, message);
        var outbox = Path.Combine(state, "outbox"); RejectLinks(outbox);
        AtomicJson(Path.Combine(outbox, item.EventId + ".json"), item);
        var audit = Path.Combine(state, "audit.jsonl"); RejectLinks(audit);
        using var log = new FileStream(audit, FileMode.Append, FileAccess.Write, FileShare.Read);
        log.Write(System.Text.Encoding.UTF8.GetBytes(JsonSerializer.Serialize(item) + "\n")); log.Flush(true);
        Console.WriteLine($"{item.Ts} {kind}: {relative} — {message}");
    }

    public void Scan()
    {
        try
        {
            foreach (var directory in new[] { root, repository, state })
            {
                RejectLinks(directory);
                if (!Directory.Exists(directory)) throw new IOException("A configured directory is unavailable; recovery is paused.");
            }
            // A complete traversal is required before any absent file can be called deleted.
            var found = new HashSet<string>(OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);
            var pending = new Stack<string>(); pending.Push(root);
            while (pending.TryPop(out var directory))
            {
                foreach (var path in Directory.EnumerateFileSystemEntries(directory))
                {
                    var attributes = File.GetAttributes(path);
                    if ((attributes & FileAttributes.ReparsePoint) != 0) continue;
                    if ((attributes & FileAttributes.Directory) != 0) { pending.Push(path); continue; }
                    var relative = Path.GetRelativePath(root, path).Replace(Path.DirectorySeparatorChar, '/');
                    if (Excluded(relative)) continue;
                    found.Add(relative);
                    Capture(relative);
                }
            }
            foreach (var item in histories.ToArray())
            {
                if (found.Contains(item.Key)) { item.Value.MissingReported = false; continue; }
                if (item.Value.ProtectionSuspended is not null)
                {
                    if (!item.Value.MissingReported) Emit("restore_failed", item.Key, item.Value.Versions[^1], item.Value.ProtectionSuspended);
                    item.Value.MissingReported = true; continue;
                }
                if (options.AutoRestore) Restore(item.Key, item.Value);
                else if (!item.Value.MissingReported)
                { Emit("delete_observed", item.Key, item.Value.Versions[^1], "Automatic restore is disabled by the local policy."); item.Value.MissingReported = true; }
            }
            Save();
            Status = histories.Values.Any(h => h.ProtectionSuspended is not null || h.MissingReported) ? "degraded" : "healthy";
            StatusMessage = $"{histories.Count} versioned files. Auto-restore: {options.AutoRestore}. Local lab policy; review recovery issues.";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException or CryptographicException)
        {
            Status = "degraded"; StatusMessage = ex.Message;
            Emit("scan_failed", "", null, "Recovery paused: " + ex.Message);
        }
    }

    private void Capture(string relative)
    {
        string path = SafePath(relative);
        var before = new FileInfo(path);
        long length = before.Length; var modified = before.LastWriteTimeUtc;
        if (length > options.MaxFileBytes)
        {
            // An oversized current file must not be replaced with an older version after deletion.
            if (histories.TryGetValue(relative, out var previous))
            { previous.ProtectionSuspended = "The last observed file exceeded the size limit; automatic restoration of an older copy is paused."; Save(); }
            throw new IOException("File exceeds the configured lab size limit: " + relative);
        }
        if (DateTime.UtcNow - modified < TimeSpan.FromMilliseconds(options.SettleMilliseconds)) return;
        var temp = Path.Combine(repository, "objects", ".fileguard-" + Guid.NewGuid().ToString("N") + ".tmp"); RejectLinks(temp);
        try
        {
            using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (var output = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { input.CopyTo(output); output.Flush(true); }
            var after = new FileInfo(path);
            if (after.Length != length || after.LastWriteTimeUtc != modified) return;
            string hash = Hash(temp);
            if (histories.TryGetValue(relative, out var history) && history.Versions[^1].Sha256 == hash)
            { history.ProtectionSuspended = null; return; }
            var version = new FileVersion(Guid.NewGuid().ToString("N"), hash, length, modified, DateTime.UtcNow);
            var destination = Blob(version);
            if (File.Exists(destination)) { if (Hash(destination) != hash) throw new InvalidDataException("Repository object integrity failure"); }
            else File.Move(temp, destination, false);
            history ??= new(); history.ProtectionSuspended = null; history.Versions.Add(version); histories[relative] = history;
            Save(); Emit("version_captured", relative, version, "Stable content preserved and SHA-256 verified.");
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }

    private void Restore(string relative, FileHistory history)
    {
        var version = history.Versions[^1];
        var destination = SafePath(relative);
        if (File.Exists(destination) || Directory.Exists(destination))
        {
            if (!history.MissingReported) Emit("restore_conflict", relative, version, "The destination exists; it was not overwritten.");
            history.MissingReported = true; return;
        }
        if (!Directory.Exists(Path.GetDirectoryName(destination)))
        {
            if (!history.MissingReported) Emit("restore_failed", relative, version, "The parent directory is missing. Directory recovery needs administrator review.");
            history.MissingReported = true; return;
        }
        history.Restores.RemoveAll(t => t < DateTime.UtcNow.AddMinutes(-1));
        if (history.Restores.Count >= options.MaxRestoresPerMinute)
        {
            if (!history.MissingReported) Emit("loop_suppressed", relative, version, "Repeated deletion exceeded the per-file restore limit. Review the incident.");
            history.MissingReported = true; return;
        }
        string source = Blob(version);
        if (!File.Exists(source) || Hash(source) != version.Sha256)
        {
            if (!history.MissingReported) Emit("restore_failed", relative, version, "The protected version is missing or its SHA-256 is invalid.");
            history.MissingReported = true; return;
        }
        var temp = Path.Combine(Path.GetDirectoryName(destination)!, ".fileguard-restore-" + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            RejectLinks(temp);
            using (var input = new FileStream(source, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (var output = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { input.CopyTo(output); output.Flush(true); }
            if (Hash(temp) != version.Sha256) throw new IOException("Restore copy failed integrity verification");
            // Recheck path ancestors immediately before the atomic, no-overwrite promotion.
            SafePath(relative); File.SetLastWriteTimeUtc(temp, version.ModifiedUtc);
            try { File.Move(temp, destination, false); }
            catch (IOException) when (File.Exists(destination) || Directory.Exists(destination))
            { Emit("restore_conflict", relative, version, "A same-name destination appeared during recovery; it was not overwritten."); return; }
            if (Hash(destination) != version.Sha256) throw new IOException("Restored content could not be verified");
            history.Restores.Add(DateTime.UtcNow); history.MissingReported = false; Save();
            Emit("restored", relative, version, "Deleted content restored and verified. This was post-delete recovery, not prevention.");
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
    public static string Hash(string path)
    {
        RejectLinks(path);
        using var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        return Convert.ToHexStringLower(SHA256.HashData(input));
    }
    public void Dispose() => instanceLock.Dispose();
}
