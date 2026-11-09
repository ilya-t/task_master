const assert = require('node:assert/strict');
const { test } = require('node:test');
const { ExtensionHarness } = require('./harness.cjs');

test('the first matching profile in the effective object supplies the invocation', t => {
    // Arrange
    const harness = new ExtensionHarness(t, { configuration: { profiles: {
        Other: { files: '*.txt', executable: 'other' },
        Specific: { files: '**/*.md', executable: 'first' },
        Fallback: { files: '**/*.md', executable: 'second' },
    } } });
    // Act
    harness.save('/data/task.md');
    // Assert
    assert.deepEqual(harness.records(), [{ executable: 'first', args: ['/data/task.md'],
        options: { cwd: '/data', shell: false, stdio: ['ignore', 'pipe', 'pipe'] } }]);
    assert.match(harness.log, /profile: Specific/);
});

test('home paths expand and processor text remains a single literal argument', t => {
    // Arrange
    const harness = new ExtensionHarness(t, { configuration: { profiles: { Home: {
        executable: '~/bin/runner a', files: '~/data/**/*.md', params: {
            archive: '~/data/archive.md', config: '~/settings/config.json',
            'experimental-archived-links-processor': 'python3 ~/script ${workspaceFolder} $(echo literal)',
        },
    } } } });
    // Act
    harness.save("/test/task-master-companion/test home/data/a ' b.md");
    // Assert
    assert.deepEqual(harness.records(), [{
        executable: '/test/task-master-companion/test home/bin/runner a',
        args: ['--archive=/test/task-master-companion/test home/data/archive.md',
            '--config=/test/task-master-companion/test home/settings/config.json',
            '--experimental-archived-links-processor=python3 ~/script ${workspaceFolder} $(echo literal)',
            "/test/task-master-companion/test home/data/a ' b.md"],
        options: { cwd: '/test/task-master-companion/test home/data', shell: false, stdio: ['ignore', 'pipe', 'pipe'] },
    }]);
});

test('workspace-relative paths and all path parameters use the containing workspace', t => {
    // Arrange
    const harness = new ExtensionHarness(t, { folders: [{ path: '/workspace' }], configuration: { profiles: { Project: {
        executable: '${workspaceFolder}/run', files: 'notes/**/*.md', params: {
            archive: './archive.md', config: '${workspaceFolder}/config.json',
            'executions-dir': 'executions', 'memories-dir': 'memories', reminders: true,
        },
    } } } });
    // Act
    harness.save('/workspace/notes/deep/task.md');
    // Assert
    assert.deepEqual(harness.records(), [{ executable: '/workspace/run', args: [
        '--archive=/workspace/archive.md', '--config=/workspace/config.json',
        '--executions-dir=/workspace/executions', '--memories-dir=/workspace/memories',
        '--reminders', '/workspace/notes/deep/task.md',
    ], options: { cwd: '/workspace/notes/deep', shell: false, stdio: ['ignore', 'pipe', 'pipe'] } }]);
});

test('outside files resolve relative executable and parameters from their directory', t => {
    const harness = new ExtensionHarness(t, { configuration: { profiles: { Outside: {
        executable: './tools/run', files: '*.md', params: { archive: './archive.md' },
    } } } });
    harness.save('/outside/task.md');
    assert.deepEqual(harness.records(), [{ executable: '/outside/tools/run',
        args: ['--archive=/outside/archive.md', '/outside/task.md'],
        options: { cwd: '/outside', shell: false, stdio: ['ignore', 'pipe', 'pipe'] } }]);
});

test('an invalid selected profile prevents fallback to the next profile', t => {
    const harness = new ExtensionHarness(t, { configuration: {
        profiles: {
            Missing: { files: '*.md' }, Fallback: { files: '*.md', executable: 'wrong' },
        },
    } });
    harness.save('/data/task.md');
    assert.deepEqual(harness.records(), []);
    assert.match(harness.notifications[0].message, /Profile "Missing": executable must be a string/);
});

for (const { name, inputs, expected } of [
    { name: 'missing files', inputs: { files: undefined }, expected: /files must be a string/ },
    { name: 'unknown parameter', inputs: { params: { unknown: 'x' } }, expected: /Unknown field or parameter "unknown"/ },
    { name: 'numeric archive', inputs: { params: { archive: 42 } }, expected: /params.archive must be a string/ },
]) {
    test(`${name} reports a labelled error without launching`, t => {
        const harness = new ExtensionHarness(t, { configuration: { profiles: { Invalid: {
            executable: 'run', files: '*.md', ...inputs,
        } } } });
        harness.save('/data/task.md');
        assert.deepEqual(harness.records(), []);
        assert.match(harness.notifications[0].message, /Profile "Invalid"/);
        assert.match(harness.notifications[0].message, expected);
    });
}

test('an absolute pattern ignores the same filename elsewhere', t => {
    const harness = new ExtensionHarness(t, { configuration: { profiles: {
        Exact: { executable: 'run', files: '/data/task.md' },
    } } });
    harness.save('/other/task.md');
    assert.deepEqual(harness.records(), []);
    assert.equal(harness.log, '');
});

test('empty profiles prompt once and open extension settings', async t => {
    const harness = new ExtensionHarness(t, { configuration: { profiles: {} } });
    harness.save();
    harness.save();
    await Promise.resolve();
    assert.deepEqual(harness.records(), []);
    assert.equal(harness.informationMessages.length, 1);
    assert.deepEqual(harness.executedCommands, [['workbench.action.openSettings', '@ext:ilya-t.task-master-companion']]);
});

for (const { name, inputs, expected } of [
    { name: 'true', inputs: { verbose: true }, expected: [true] },
    { name: 'false', inputs: { verbose: false }, expected: [] },
]) {
    test(`verbose ${name} controls panel opening on save`, t => {
        const harness = new ExtensionHarness(t, { configuration: { profiles: {
            Logged: { executable: 'run', files: '*.md', ...inputs },
        } } });
        harness.save('/data/task.md');
        assert.deepEqual(harness.shownLogs, expected);
    });
}

test('configuration errors are reported once until settings change and retain Open Log', async t => {
    // Arrange
    const settings = { profiles: { Missing: { files: '*.md' } } };
    const harness = new ExtensionHarness(t, { configuration: settings });
    // Act
    harness.save();
    harness.save();
    harness.setConfiguration(settings);
    harness.save();
    await Promise.resolve();
    // Assert
    assert.deepEqual(harness.records(), []);
    assert.equal(harness.notifications.length, 2);
    assert.deepEqual(harness.shownLogs, [true, true]);
});

test('settings changes preserve the active process and apply on the next launch', t => {
    // Arrange
    const harness = new ExtensionHarness(t, { configuration: { profiles: {
        Before: { executable: 'before', files: '*.md', params: { config: '/before.json' } },
    } } });
    harness.save('/data/task.md');
    const current = harness.processes[0];
    // Act
    harness.setConfiguration({ profiles: { After: { executable: 'after', files: '*.md', params: { config: '/after.json' } } } });
    harness.save('/data/task.md');
    current.finish();
    harness.save('/data/task.md');
    // Assert
    assert.deepEqual(current.signals, []);
    assert.deepEqual(harness.records().map(record => [record.executable, record.args]), [
        ['before', ['--config=/before.json', '/data/task.md']],
        ['after', ['--config=/after.json', '/data/task.md']],
    ]);
});

test('multi-root folders use their own effective profile object and workspace variable', t => {
    // Arrange
    const harness = new ExtensionHarness(t, { folders: [
        { path: '/alpha', configuration: { profiles: { Alpha: {
            executable: '${workspaceFolder}/run', files: '${workspaceFolder}/data/*.md',
        } } } },
        { path: '/beta', configuration: { profiles: { Beta: {
            executable: '${workspaceFolder}/run', files: '${workspaceFolder}/data/*.md',
        } } } },
    ] });
    // Act
    harness.save('/alpha/data/task.md');
    harness.processes[0].finish();
    harness.save('/beta/data/task.md');
    // Assert
    assert.deepEqual(harness.records().map(record => [record.executable, record.args]), [
        ['/alpha/run', ['/alpha/data/task.md']], ['/beta/run', ['/beta/data/task.md']],
    ]);
});
