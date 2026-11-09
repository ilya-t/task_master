const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const { ExtensionHarness } = require('./harness.cjs');

test('saving another name or a non-file URI does not start Task Master', t => {
    const harness = new ExtensionHarness(t);
    harness.save(path.join(path.dirname(harness.filePath), 'other.md'));
    harness.save(path.join(path.dirname(harness.filePath), 'DOCUMENT.md'));
    harness.save(harness.filePath, 'untitled');
    harness.save(harness.filePath, 'vscode-remote');
    assert.equal(harness.log, '');
    assert.deepEqual(harness.records(), []);
});

test('an untrusted workspace does not subscribe to saved documents', t => {
    const harness = new ExtensionHarness(t, { isTrusted: false });
    harness.save();
    assert.equal(harness.savedDocuments.listenerCount('save'), 0);
    assert.deepEqual(harness.records(), []);
});

test('saves during processing are skipped across files without a deferred run', t => {
    // Arrange
    const harness = new ExtensionHarness(t);
    harness.save();
    // Act
    harness.save();
    harness.save(path.join(harness.directory, 'another', 'document.md'));
    harness.processes[0].finish();
    // Assert
    assert.equal(harness.log.split('Skipped while Task Master is running:').length - 1, 2, harness.log);
    assert.deepEqual(harness.records().map(record => record.args.at(-1)), [harness.filePath]);
});

test('a nonzero exit reports an error and allows the next save', async t => {
    // Arrange
    const harness = new ExtensionHarness(t);
    harness.save();
    // Act
    harness.processes[0].emit('exit', 7, null);
    harness.save();
    await Promise.resolve();
    // Assert
    assert.equal(harness.records().length, 2);
    assert.deepEqual(harness.notifications, [{
        message: `Task Master failed for ${harness.filePath} (code: 7, signal: none).`,
        actions: ['Open Log'],
    }]);
    assert.deepEqual(harness.shownLogs, [true]);
});

test('the next save starts after exit while inherited output pipes remain open', t => {
    const harness = new ExtensionHarness(t);
    harness.save();
    harness.processes[0].emit('exit', 0, null);
    harness.save();
    assert.deepEqual(harness.records().map(record => record.args.at(-1)), [harness.filePath, harness.filePath]);
    assert.match(harness.log, /Finished Task Master:.*code: 0/);
    assert.deepEqual(harness.notifications, []);
});

test('a delayed close from the previous process keeps the new process locked', t => {
    // Arrange
    const harness = new ExtensionHarness(t);
    harness.save();
    const previous = harness.processes[0];
    previous.emit('exit', 0, null);
    harness.save();
    assert.equal(harness.processes.length, 2);
    // Act
    previous.emit('close', 0, null);
    harness.save();
    // Assert
    assert.equal(harness.records().length, 2);
    assert.match(harness.log, /Skipped while Task Master is running:/);
    assert.equal(harness.log.split('Finished Task Master:').length - 1, 1);
});

test('a missing executable reports a launch error and allows the next save', t => {
    // Arrange
    const harness = new ExtensionHarness(t);
    harness.save();
    // Act
    harness.processes[0].fail(new Error('spawn ENOENT'));
    harness.save();
    // Assert
    assert.deepEqual(harness.records().map(record => record.args.at(-1)), [harness.filePath, harness.filePath]);
    assert.deepEqual(harness.notifications, [{
        message: `Task Master failed for ${harness.filePath}: spawn ENOENT`,
        actions: ['Open Log'],
    }]);
    assert.match(harness.log, /spawn ENOENT/);
});

test('a delayed close after a spawn failure does not unlock the replacement process', t => {
    // Arrange
    const harness = new ExtensionHarness(t);
    harness.save();
    const failed = harness.processes[0];
    failed.fail(new Error('spawn ENOENT'));
    harness.save();
    assert.equal(harness.processes.length, 2);
    // Act
    failed.emit('close', -2, null);
    harness.save();
    // Assert
    assert.equal(harness.records().length, 2);
    assert.equal(harness.notifications.length, 1);
    assert.match(harness.log, /Skipped while Task Master is running:/);
});

test('stdout, stderr and the result appear in the output channel', t => {
    const harness = new ExtensionHarness(t);
    harness.save();
    const child = harness.processes[0];
    child.stdout.write('value-a 🌍\n');
    child.stderr.write('value-b\n');
    child.finish();
    assert.match(harness.log, /value-a 🌍\n/);
    assert.match(harness.log, /value-b\n/);
    assert.ok(harness.log.includes(`Finished Task Master: ${harness.filePath} (code: 0, signal: none)`));
});

test('deactivation unsubscribes, requests process termination and disposes output', t => {
    // Arrange
    const harness = new ExtensionHarness(t);
    harness.save();
    const child = harness.processes[0];
    // Act
    harness.extension.deactivate();
    child.stdout.write('late output');
    child.finish(null, 'SIGTERM');
    // Assert
    assert.equal(harness.savedDocuments.listenerCount('save'), 0);
    assert.equal(harness.outputDisposed, true);
    assert.deepEqual(child.signals, ['SIGTERM']);
});
