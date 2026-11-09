const { EventEmitter } = require('node:events');

class Position {
    constructor(line, character) {
        this.line = line;
        this.character = character;
    }

    isEqual(other) {
        return this.line === other.line && this.character === other.character;
    }
}

class Selection {
    constructor(anchor, active) {
        this.anchor = anchor;
        this.active = active;
    }
}

class EditorEnvironment {
    constructor() {
        this.events = new EventEmitter();
        this.api = {
            Position,
            Selection,
            workspace: {
                textDocuments: [],
                onDidOpenTextDocument: callback => subscribe(this.events, 'open', callback),
                onDidCloseTextDocument: callback => subscribe(this.events, 'close', callback),
                onDidChangeTextDocument: callback => subscribe(this.events, 'change', callback),
            },
            window: {
                visibleTextEditors: [],
                onDidChangeVisibleTextEditors: callback => subscribe(this.events, 'visible', callback),
                onDidChangeTextEditorSelection: callback => subscribe(this.events, 'selection', callback),
            },
        };
    }

    openEditor(filePath, text, selections, scheme = 'file') {
        const document = {
            uri: { fsPath: filePath, scheme },
            text,
            version: 1,
            isDirty: false,
            isClosed: false,
            getText() { return this.text; },
        };
        this.api.workspace.textDocuments.push(document);
        this.events.emit('open', document);
        return this.showDocument(document, selections);
    }

    showDocument(document, selections) {
        const editor = { document, savedSelections: selections, selectionWrites: 0 };
        Object.defineProperty(editor, 'selections', {
            get: () => editor.savedSelections,
            set: value => {
                editor.selectionWrites++;
                editor.savedSelections = value;
                queueMicrotask(() => this.events.emit('selection', {
                    textEditor: editor, selections: value, kind: 3,
                }));
            },
        });
        this.api.window.visibleTextEditors.push(editor);
        this.events.emit('visible', this.api.window.visibleTextEditors);
        return editor;
    }

    changeDocument(document, text, { isDirty = false, reason } = {}) {
        document.text = text;
        document.version++;
        document.isDirty = isDirty;
        this.events.emit('change', { document, contentChanges: [{ text }], reason });
    }

    moveSelections(editor, selections, kind) {
        editor.savedSelections = selections;
        this.events.emit('selection', { textEditor: editor, selections, kind });
    }

    closeDocument(document) {
        document.isClosed = true;
        this.api.workspace.textDocuments = this.api.workspace.textDocuments.filter(item => item !== document);
        this.api.window.visibleTextEditors = this.api.window.visibleTextEditors.filter(editor => editor.document !== document);
        this.events.emit('close', document);
        this.events.emit('visible', this.api.window.visibleTextEditors);
    }
}

function subscribe(emitter, event, callback) {
    emitter.on(event, callback);
    return { dispose: () => emitter.off(event, callback) };
}

module.exports = { EditorEnvironment, Position, Selection };
