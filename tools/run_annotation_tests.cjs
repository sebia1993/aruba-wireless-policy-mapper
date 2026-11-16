/* Expand test paths in Node so npm works identically in Windows and POSIX shells. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const directory = path.resolve(__dirname, '../tests/js');
const files = fs.readdirSync(directory).filter(name => name.endsWith('.test.js')).sort();
if (!files.length) throw new Error('No annotation test files found.');
const result = spawnSync(process.execPath, ['--test', ...files.map(name => path.join(directory, name))], {stdio:'inherit'});
if (result.error) throw result.error;
process.exitCode = result.status === null ? 1 : result.status;
