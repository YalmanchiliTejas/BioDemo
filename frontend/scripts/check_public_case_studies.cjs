/* The public entry points now expose only the current freeze-drying study. */
const {execFileSync} = require('node:child_process');
const path = require('node:path');
execFileSync(process.execPath, [path.join(__dirname, 'check_lyo_study.cjs'), process.argv[2] || 'http://127.0.0.1:5186'], {
  stdio: 'inherit',
  env: {...process.env, AGENT_BROWSER_SESSION: process.env.AGENT_BROWSER_SESSION || `sievance-current-study-${process.pid}`},
});
