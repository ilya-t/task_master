const assert = require('node:assert/strict');
const os = require('node:os');
const path = require('node:path');
const { EventEmitter } = require('node:events');
const mockRequire = require('mock-require');
const { EditorEnvironment } = require('./editor_environment.cjs');
const { ProcessStub } = require('./process_stub.cjs');

class ExtensionHarness {
    constructor(test, { isTrusted = true, configuration, folders = [] } = {}) {
        this.directory = '/test/task-master-companion';
        this.userDirectory = path.join(this.directory, 'test home');
        this.filePath = path.join(this.directory, "project $(echo injected) ' spaced", 'document.md');
        this.log = '';
        this.notifications = [];
        this.shownLogs = [];
        this.outputDisposed = false;
        this.savedDocuments = new EventEmitter();
        this.context = { subscriptions: [] };
        this.invocations = [];
        this.processes = [];
        this.settings = configuration ?? {
            profiles: { A: { executable: '~/bin/runner', files: '**/document.md' } },
        };
        this.folders = folders;
        this.informationMessages = [];
        this.executedCommands = [];
        this.notificationAction = 'Open Log';
        test.mock.method(os, 'homedir', () => this.userDirectory);
        this.editorEnvironment = new EditorEnvironment();
        const api = {
            ...this.editorEnvironment.api,
            RelativePattern: class {
                constructor(base, pattern) {
                    this.baseUri = { fsPath: base };
                    this.pattern = pattern;
                }
            },
            languages: {
                match: (selector, document) => {
                    if (selector.scheme !== document.uri.scheme) {
                        return 0;
                    }
                    const pattern = selector.pattern;
                    // Substitute the VS Code glob boundary with Node's built-in matcher.
                    if (typeof pattern === 'string') {
                        return path.matchesGlob(document.uri.fsPath, pattern) ? 10 : 0;
                    }
                    const relative = path.relative(pattern.baseUri.fsPath, document.uri.fsPath);
                    return path.matchesGlob(relative, pattern.pattern) ? 10 : 0;
                },
            },
            commands: {
                executeCommand: async (...args) => { this.executedCommands.push(args); },
            },
            workspace: {
                ...this.editorEnvironment.api.workspace,
                isTrusted,
                getConfiguration: (section, uri) => {
                    assert.equal(section, 'taskMasterCompanion');
                    const settings = this.folderFor(uri)?.configuration ?? this.settings;
                    return { get: (key, fallback) => settings[key] === undefined ? fallback : settings[key] };
                },
                getWorkspaceFolder: uri => {
                    const folder = this.folderFor(uri);
                    return folder ? { uri: { fsPath: folder.path } } : undefined;
                },
                onDidChangeConfiguration: callback => {
                    this.editorEnvironment.events.on('configuration', callback);
                    return { dispose: () => this.editorEnvironment.events.off('configuration', callback) };
                },
                onDidSaveTextDocument: callback => {
                    this.savedDocuments.on('save', callback);
                    return { dispose: () => this.savedDocuments.off('save', callback) };
                },
            },
            window: {
                ...this.editorEnvironment.api.window,
                createOutputChannel: name => {
                    assert.equal(name, 'Task Master Companion');
                    return {
                        append: value => this.appendOutput(value),
                        appendLine: value => this.appendOutput(value + '\n'),
                        show: preserveFocus => this.shownLogs.push(preserveFocus),
                        dispose: () => { this.outputDisposed = true; },
                    };
                },
                showErrorMessage: async (message, ...actions) => {
                    this.notifications.push({ message, actions });
                    return this.notificationAction;
                },
                showInformationMessage: async (message, ...actions) => {
                    this.informationMessages.push({ message, actions });
                    return 'Open Settings';
                },
            },
        };
        this.editorEnvironment.api = api;
        mockRequire('vscode', api);
        mockRequire('node:child_process', {
            spawn: (executable, args, options) => {
                const child = new ProcessStub();
                this.invocations.push({ executable, args, options });
                this.processes.push(child);
                return child;
            },
        });
        mockRequire.reRequire('../out/companion_configuration.js');
        mockRequire.reRequire('../out/position_mapper.js');
        mockRequire.reRequire('../out/cursor_preserver.js');
        mockRequire.reRequire('../out/task_master_companion.js');
        this.extension = mockRequire.reRequire('../out/extension.js');
        test.after(() => {
            this.extension.deactivate();
            for (const disposable of this.context.subscriptions) {
                disposable.dispose();
            }
            mockRequire.stop('vscode');
            mockRequire.stop('node:child_process');
        });
        this.extension.activate(this.context);
    }

    save(filePath = this.filePath, scheme = 'file') {
        this.savedDocuments.emit('save', { uri: { scheme, fsPath: filePath } });
    }

    folderFor(uri) {
        return this.folders.filter(folder => uri.fsPath.startsWith(folder.path + '/'))
            .sort((left, right) => right.path.length - left.path.length)[0];
    }

    setConfiguration(settings) {
        this.settings = settings;
        this.editorEnvironment.events.emit('configuration', {
            affectsConfiguration: section => section === 'taskMasterCompanion',
        });
    }

    records() {
        return this.invocations;
    }

    appendOutput(value) {
        assert.equal(this.outputDisposed, false, 'must not write to a disposed channel');
        this.log += value;
    }
}

module.exports = { ExtensionHarness };
