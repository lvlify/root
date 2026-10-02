'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { TextDecoder } = require('node:util');

function body() {
  const source = path.join(__dirname, '..', 'skills', 'root', 'SKILL.md');
  const text = new TextDecoder('utf-8', { fatal: true })
    .decode(fs.readFileSync(source)).replace(/\r\n/g, '\n');
  const match = /^---\n([\s\S]*?)\n---\n([\s\S]+)$/.exec(text);
  if (!match || !/^name: root$/m.test(match[1]) || !match[2].trim()) {
    throw new Error(`${source}: expected a nonempty root skill`);
  }
  const context = match[2].trim();
  if (Buffer.byteLength(context, 'utf8') > 8192) {
    throw new Error(`${source}: root body exceeds the 8 KiB context limit`);
  }
  return context;
}

function emit(event) {
  try {
    if (!['SessionStart', 'SubagentStart', 'copilot'].includes(event)) {
      throw new Error('unknown root hook event');
    }
    const context = body();
    const output = event === 'copilot' ? { additionalContext: context }
      : { hookSpecificOutput: { hookEventName: event, additionalContext: context } };
    process.stdout.write(JSON.stringify(output) + '\n');
  } catch (error) {
    process.stderr.write(`root: ${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { body, emit };
if (require.main === module) emit(process.argv[2]);
