using System.Net.Http.Json;
using System.Text.Json;
using FileGuard.Recovery;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

if (args.Length != 2 || args[0] != "--config")
{
    Console.Error.WriteLine("Usage: FileGuard.Recovery --config <protected-local-config.json>");
    return 2;
}
var configPath = Path.GetFullPath(args[1]);
var options = JsonSerializer.Deserialize<RecoveryOptions>(File.ReadAllText(configPath), RecoveryEngine.Json)
    ?? throw new InvalidDataException("Recovery configuration is empty.");
var builder = Host.CreateApplicationBuilder(Array.Empty<string>());
builder.Services.AddWindowsService(o => o.ServiceName = "NileHopeFileGuardRecoveryPilot");
builder.Services.AddSingleton(options);
builder.Services.AddHostedService<RecoveryWorker>();
await builder.Build().RunAsync();
return 0;

sealed class RecoveryWorker(RecoveryOptions options, ILogger<RecoveryWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var engine = new RecoveryEngine(options);
        using var changed = new SemaphoreSlim(0, 1);
        using var watcher = new FileSystemWatcher(options.ProtectedRoot)
        { IncludeSubdirectories = true, NotifyFilter = NotifyFilters.FileName | NotifyFilters.LastWrite | NotifyFilters.Size };
        // Watcher is a hint; periodic complete scans reconcile dropped notifications.
        watcher.Error += (_, e) => logger.LogWarning(e.GetException(), "Watcher notification gap; complete scans continue.");
        void Wake() { try { changed.Release(); } catch (SemaphoreFullException) { } }
        watcher.Changed += (_, _) => Wake(); watcher.Created += (_, _) => Wake();
        watcher.Deleted += (_, _) => Wake(); watcher.Renamed += (_, _) => Wake();
        watcher.EnableRaisingEvents = true;
        using var reporter = new Reporter(options);
        using var reportStop = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        // Management latency cannot hold up the local scan/restore loop.
        var reports = Task.Run(async () =>
        {
            while (!reportStop.IsCancellationRequested)
            {
                try { await reporter.Send(engine.Status, engine.StatusMessage, reportStop.Token); }
                catch (Exception e) when (e is HttpRequestException or TaskCanceledException or IOException or JsonException)
                { logger.LogWarning("Management is unavailable; events remain in the durable local outbox. {Reason}", e.Message); }
                try { await Task.Delay(TimeSpan.FromSeconds(5), reportStop.Token); }
                catch (OperationCanceledException) when (reportStop.IsCancellationRequested) { break; }
            }
        }, CancellationToken.None);
        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                engine.Scan();
                try { await changed.WaitAsync(TimeSpan.FromSeconds(options.ScanSeconds), stoppingToken); }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            }
        }
        finally { await reportStop.CancelAsync(); await reports; }
    }
}

sealed class Reporter : IDisposable
{
    private readonly RecoveryOptions options;
    private readonly HttpClient? http;
    private readonly string credentialPath;
    public Reporter(RecoveryOptions options)
    {
        this.options = options; credentialPath = Path.Combine(options.StateRoot, "device-credential.json");
        if (string.IsNullOrWhiteSpace(options.ServerUrl)) return;
        var uri = new Uri(options.ServerUrl.TrimEnd('/') + "/");
        if (uri.Scheme != "https" && !(uri.Scheme == "http" && uri.IsLoopback && options.AllowInsecureLoopback))
            throw new ArgumentException("Agent communication requires HTTPS; only an explicitly enabled loopback lab may use HTTP.");
        if (uri.UserInfo.Length != 0 || uri.Query.Length != 0 || uri.Fragment.Length != 0 || uri.AbsolutePath != "/")
            throw new ArgumentException("Use the console origin without credentials, query or subpath.");
        http = new HttpClient { BaseAddress = uri, Timeout = TimeSpan.FromSeconds(10) };
        http.DefaultRequestHeaders.Add("X-Device", options.Hostname);
    }
    public async Task Send(string status, string message, CancellationToken cancel)
    {
        if (http is null) return;
        if (!http.DefaultRequestHeaders.Contains("X-Api-Key"))
        {
            string key;
            if (File.Exists(credentialPath)) key = JsonSerializer.Deserialize<Dictionary<string, string>>(File.ReadAllText(credentialPath))!["key"];
            else
            {
                using var response = await http.PostAsJsonAsync("api/agent/enroll", new { token = options.EnrollmentToken, hostname = options.Hostname, ring = "pilot" }, cancel);
                response.EnsureSuccessStatusCode();
                key = (await response.Content.ReadFromJsonAsync<Dictionary<string, string>>(cancel))!["key"];
                RecoveryEngine.AtomicJson(credentialPath, new { key });
            }
            http.DefaultRequestHeaders.Add("X-Api-Key", key);
        }
        using (var heartbeat = await http.PostAsJsonAsync("api/agent/heartbeat", new
        {
            os_family = OperatingSystem.IsWindows() ? "windows" : "linux",
            os_version = System.Runtime.InteropServices.RuntimeInformation.OSDescription,
            architecture = System.Runtime.InteropServices.RuntimeInformation.OSArchitecture.ToString(),
            agent_version = "0.2.0-recovery-pilot", department = "Disposable recovery pilot",
            monitoring_status = status, monitoring_message = message
        }, cancel)) heartbeat.EnsureSuccessStatusCode();
        using (var report = await http.PostAsJsonAsync("api/agent/recovery-status", new
        {
            hostName = Environment.MachineName,
            mode = options.AutoRestore ? "recovery" : "monitoring",
            protectedRoot = options.ProtectedRoot,
            monitoringStatus = status,
            message,
        }, cancel)) report.EnsureSuccessStatusCode();
        foreach (var path in Directory.EnumerateFiles(Path.Combine(options.StateRoot, "outbox"), "*.json").Order().Take(100))
        {
            var item = JsonSerializer.Deserialize<RecoveryEvent>(File.ReadAllText(path), RecoveryEngine.Json)
                ?? throw new InvalidDataException("Empty queued recovery event");
            using var result = await http.PostAsJsonAsync("api/agent/recovery-events", new { events = new[] { item } }, cancel);
            result.EnsureSuccessStatusCode();
            File.Delete(path); // Only acknowledged events leave the outbox. Server deduplicates event IDs.
        }
    }
    public void Dispose() => http?.Dispose();
}
