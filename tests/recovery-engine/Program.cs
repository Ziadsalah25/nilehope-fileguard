using FileGuard.Recovery;
using System.Text.Json;

int passed = 0;
void Test(string name, Action<Lab> check)
{
    using var lab = new Lab();
    check(lab); Console.WriteLine("PASS: " + name); passed++;
}
void Assert(bool condition, string detail) { if (!condition) throw new Exception(detail); }

Test("stable baseline, modification, deletion and hash-verified restore", lab =>
{
    File.WriteAllText(lab.File, "version one");
    using var engine = new RecoveryEngine(lab.Options);
    engine.Scan();
    File.WriteAllText(lab.File, "version two"); engine.Scan();
    Assert(engine.Histories["sample.txt"].Versions.Count == 2, "Both versions must be recoverable.");
    File.Delete(lab.File); engine.Scan();
    Assert(File.ReadAllText(lab.File) == "version two", "Restore must use the latest stable copy.");
    Assert(RecoveryEngine.Hash(lab.File) == engine.Histories["sample.txt"].Versions[^1].Sha256, "Restored hash differs.");
});
Test("manifest and repeated-delete limit survive restart", lab =>
{
    File.WriteAllText(lab.File, "original");
    using (var first = new RecoveryEngine(lab.Options)) { first.Scan(); File.Delete(lab.File); first.Scan(); }
    using var restarted = new RecoveryEngine(lab.Options with { MaxRestoresPerMinute = 1 });
    File.Delete(lab.File); restarted.Scan();
    Assert(!File.Exists(lab.File), "Repeated deletion should stop at the configured limit.");
    Assert(lab.Events().Any(e => e.Kind == "loop_suppressed"), "Suppression must be reported.");
});
Test("corrupt repository object is never restored", lab =>
{
    File.WriteAllText(lab.File, "valid");
    using var engine = new RecoveryEngine(lab.Options); engine.Scan();
    File.WriteAllText(Directory.GetFiles(Path.Combine(lab.Options.RepositoryRoot, "objects"), "*.blob").Single(), "corrupted");
    File.Delete(lab.File); engine.Scan();
    Assert(!File.Exists(lab.File), "A corrupt object must not be promoted.");
    Assert(lab.Events().Any(e => e.Kind == "restore_failed"), "Integrity failure must be reported.");
});
Test("same-name conflicts and existing content are preserved", lab =>
{
    File.WriteAllText(lab.File, "original");
    using var engine = new RecoveryEngine(lab.Options); engine.Scan();
    File.WriteAllText(lab.File, "new legitimate content"); engine.Scan();
    Assert(File.ReadAllText(lab.File) == "new legitimate content", "Existing content was overwritten.");
    File.Delete(lab.File); Directory.CreateDirectory(lab.File); engine.Scan();
    Assert(Directory.Exists(lab.File), "A same-name directory must remain intact.");
    Assert(lab.Events().Any(e => e.Kind == "restore_conflict"), "Conflict must be recorded.");
});
Test("monitoring-only policy records deletion without restoring", lab =>
{
    File.WriteAllText(lab.File, "original");
    using var engine = new RecoveryEngine(lab.Options with { AutoRestore = false }); engine.Scan();
    File.Delete(lab.File); engine.Scan();
    Assert(!File.Exists(lab.File), "Auto-restore is disabled.");
    Assert(lab.Events().Any(e => e.Kind == "delete_observed"), "Deletion must be visible.");
});
Test("unavailable protected root pauses recovery", lab =>
{
    File.WriteAllText(lab.File, "original");
    using var engine = new RecoveryEngine(lab.Options); engine.Scan();
    Directory.Move(lab.Options.ProtectedRoot, lab.Options.ProtectedRoot + "-unavailable"); engine.Scan();
    Assert(engine.Status == "degraded" && !Directory.Exists(lab.Options.ProtectedRoot), "The root must not be recreated.");
});
Test("oversized observed file suspends restoration of older content", lab =>
{
    File.WriteAllText(lab.File, "small");
    using var engine = new RecoveryEngine(lab.Options with { MaxFileBytes = 10 }); engine.Scan();
    File.WriteAllText(lab.File, new string('x', 11)); engine.Scan(); File.Delete(lab.File); engine.Scan();
    Assert(!File.Exists(lab.File), "Older content should not replace a file whose protection was suspended.");
});
Test("nested repository and overlapping state are rejected", lab =>
{
    bool rejected = false;
    try { using var _ = new RecoveryEngine(lab.Options with { RepositoryRoot = Path.Combine(lab.Options.ProtectedRoot, "backup") }); }
    catch (ArgumentException) { rejected = true; }
    Assert(rejected, "Repository inside the protected tree was accepted.");
});
Test("exclusive instance lock prevents concurrent mutation", lab =>
{
    using var first = new RecoveryEngine(lab.Options);
    bool rejected = false;
    try { using var second = new RecoveryEngine(lab.Options); } catch (IOException) { rejected = true; }
    Assert(rejected, "A second writer was accepted.");
});
if (!OperatingSystem.IsWindows()) Test("links are not traversed or restored through", lab =>
{
    var outside = Path.Combine(lab.Base, "outside"); Directory.CreateDirectory(outside);
    File.WriteAllText(Path.Combine(outside, "external.txt"), "external data");
    Directory.CreateSymbolicLink(Path.Combine(lab.Options.ProtectedRoot, "linked"), outside);
    File.WriteAllText(lab.File, "protected");
    using var engine = new RecoveryEngine(lab.Options); engine.Scan();
    Assert(engine.Histories.Count == 1, "External link contents were captured.");
    File.Delete(lab.File); File.CreateSymbolicLink(lab.File, Path.Combine(outside, "external.txt")); engine.Scan();
    Assert(File.ReadAllText(Path.Combine(outside, "external.txt")) == "external data", "Recovery escaped into a symbolic link.");
    Assert(engine.Status == "degraded", "A replaced path needs review.");
});
Console.WriteLine($"{passed} recovery engine scenarios passed.");

sealed class Lab : IDisposable
{
    public string Base { get; } = Path.Combine(Path.GetTempPath(), "fileguard-test-" + Guid.NewGuid().ToString("N"));
    public RecoveryOptions Options { get; }
    public string File => Path.Combine(Options.ProtectedRoot, "sample.txt");
    public Lab()
    {
        Options = new() { ProtectedRoot = Path.Combine(Base, "protected"), RepositoryRoot = Path.Combine(Base, "repository"), StateRoot = Path.Combine(Base, "state"), AutoRestore = true, SettleMilliseconds = 0 };
        Directory.CreateDirectory(Options.ProtectedRoot); Directory.CreateDirectory(Options.RepositoryRoot); Directory.CreateDirectory(Options.StateRoot);
    }
    public IEnumerable<RecoveryEvent> Events() => System.IO.File.ReadLines(Path.Combine(Options.StateRoot, "audit.jsonl"))
        .Select(line => JsonSerializer.Deserialize<RecoveryEvent>(line, RecoveryEngine.Json)!);
    public void Dispose() => Directory.Delete(Base, true);
}
