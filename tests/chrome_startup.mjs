// Chrome chooses an available port and announces its ready endpoint on stderr.
// Keep diagnostics so crashes fail immediately with the actual browser error.
export function waitForDevTools(proc, timeout = 30000) {
  return new Promise((resolve, reject) => {
    let stderr = "";
    const cleanup = () => {
      clearTimeout(timer);
      proc.removeListener("error", onError);
      proc.removeListener("exit", onExit);
      proc.stderr.removeListener("data", onData);
      // Continue draining Chrome's diagnostics after startup.
      proc.stderr.resume();
    };
    const fail = (reason) => {
      cleanup();
      reject(new Error(`${reason}\n${stderr.trim()}`));
    };
    const onError = (error) => fail(`Chrome could not start: ${error.message}`);
    const onExit = (code, signal) => fail(`Chrome exited before DevTools was ready (code ${code}, signal ${signal})`);
    const onData = (chunk) => {
      stderr = (stderr + chunk.toString()).slice(-16384);
      const match = /DevTools listening on (ws:\/\/[^\s]+)\r?\n/.exec(stderr);
      if (match) { cleanup(); resolve(match[1]); }
    };
    const timer = setTimeout(() => fail(`Chrome did not announce DevTools within ${timeout}ms`), timeout);
    proc.stderr.on("data", onData);
    proc.once("error", onError);
    proc.once("exit", onExit);
  });
}
