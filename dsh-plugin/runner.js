import { spawn } from 'node:child_process';

/** Bounded, secret-free stdout protocol; credentials cross only stdin. */
export function runPython(config, request, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error('请求已取消'));
    const child = spawn(config.pythonPath, ['-m', 'sf_express_mcp.dsh_bridge'], {
      cwd: config.projectDir, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    let output = '';
    let done = false;
    const finish = (error, value) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      if (error) reject(error); else resolve(value);
    };
    const abort = () => {
      child.kill();
      finish(new Error('调用已中断，变更结果可能仍需核实'));
    };
    const timer = setTimeout(abort, 45000);
    signal?.addEventListener('abort', abort, { once: true });
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', chunk => {
      output += chunk;
      if (Buffer.byteLength(output, 'utf8') > 512 * 1024) abort();
    });
    // Drain diagnostics without disclosing process details or credentials.
    child.stderr.resume();
    child.on('error', () => finish(new Error('无法启动顺丰 Python 服务，请检查插件的 Python 路径')));
    child.on('close', code => {
      if (code !== 0) return finish(new Error('顺丰服务异常退出，变更结果可能仍需核实'));
      try { finish(null, JSON.parse(output)); }
      catch { finish(new Error('顺丰服务未返回有效结果，变更结果可能仍需核实')); }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify(request));
  });
}
