const assert = require('node:assert/strict');
const {start} = require('./router_autoping.cjs');
const plan = {chunks: [6877], schedulerId: 1133, settingsId: 89718};

async function main() {
  const previous = global.__quotaAutoPing;
  try {
    for (const enabled of [false, true]) {
      const settings = {claudeAutoPing: {connections: {account: enabled}}};
      let intervals = 0;
      const loaded = new Set();
      global.__quotaAutoPing = {interval: null};
      const runtime = id => {
        assert(loaded.has(6877), 'scheduler dependencies must load first');
        if (id === 89718) return {mt: async () => settings};
        assert.equal(id, 1133);
        return {configureQuotaAutoPing(value) {
          assert.equal(value, settings, 'preserve the saved account switches');
          if (value.claudeAutoPing.connections.account && !global.__quotaAutoPing.interval) {
            global.__quotaAutoPing.interval = ++intervals;
          }
        }};
      };
      runtime.e = async id => loaded.add(id);
      const load = filename => {
        if (filename === '/fixture/.next-cli-build/server/app/api/settings/route.js') return {};
        assert.equal(filename, '/fixture/.next-cli-build/server/webpack-runtime.js');
        return runtime;
      };
      assert.deepEqual(await start('/fixture', load, plan), {running: enabled});
      assert.deepEqual(await start('/fixture', load, plan), {running: enabled});
      assert.equal(intervals, enabled ? 1 : 0, 'reuse the existing scheduler');
    }
    await assert.rejects(start('/fixture', () => {
      const runtime = () => ({});
      runtime.e = async () => {};
      return runtime;
    }, plan), /Unsupported 9router scheduler build/);
    console.log('Router bootstrap: saved switches, repeated startup and incompatible builds passed');
  } finally {
    if (previous === undefined) delete global.__quotaAutoPing;
    else global.__quotaAutoPing = previous;
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
