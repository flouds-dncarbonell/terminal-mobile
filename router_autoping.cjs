// Load 9router's existing quota scheduler when started without its dashboard.
const path = require('node:path');
const fs = require('node:fs');

function discover(appDirectory) {
  const route = fs.readFileSync(path.join(appDirectory, '.next-cli-build/server/app/api/settings/route.js'), 'utf8');
  const match = route.match(/Promise\.all\(\[([^\]]+)\]\)\.then\([a-z]\.bind\([a-z],(\d+)\)\)\.then\(\(\{configureQuotaAutoPing/);
  if (!match) throw new Error('Unsupported 9router scheduler dependency graph');
  const chunks = Array.from(match[1].matchAll(/[a-z]\.e\((\d+)\)/g), value => Number(value[1]));
  if (!chunks.length) throw new Error('Missing scheduler dependencies');
  return {chunks, schedulerId: Number(match[2]), settingsId: 89718};
}

async function start(appDirectory, load = require, plan = discover(appDirectory)) {
  // Register the standalone build's database/native adapters and base modules.
  // Requiring a route only loads its definitions; it does not run its handlers.
  load(path.join(appDirectory, '.next-cli-build/server/app/api/settings/route.js'));
  const runtime = load(path.join(appDirectory, '.next-cli-build/server/webpack-runtime.js'));
  await Promise.all(plan.chunks.map(id => runtime.e(id)));
  const scheduler = await runtime(plan.schedulerId);
  const settings = await runtime(plan.settingsId);
  if (typeof scheduler.configureQuotaAutoPing !== 'function' || typeof settings.mt !== 'function') {
    throw new Error('Unsupported 9router scheduler build');
  }
  // Reuse its global interval, account switches, credentials and cooldowns.
  // Opening the dashboard later cannot create a second scheduler.
  scheduler.configureQuotaAutoPing(await settings.mt());
  return {running: Boolean(global.__quotaAutoPing?.interval)};
}

module.exports = {start, discover};

if (process.env.TERMINAL_MOBILE_ROUTER_BOOTSTRAP === '1') {
  const appDirectory = path.dirname(path.resolve(process.argv[1]));
  // Let the standalone HTTP server finish its synchronous setup first.
  setImmediate(async () => {
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        await start(appDirectory);
        console.log('[TerminalMobile] quota auto-ping initialized');
        return;
      } catch {
        console.warn(`[TerminalMobile] quota auto-ping initialization failed (${attempt}/3); check the installed 9router build`);
        if (attempt < 3) await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }
  });
}
