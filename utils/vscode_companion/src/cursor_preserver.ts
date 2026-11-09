import * as vscode from 'vscode';
import { PositionMapper } from './position_mapper';
import { CompanionConfiguration } from './companion_configuration';

interface DocumentSnapshot {
    text: string;
    version: number;
    isDirty: boolean;
}

interface EditorSnapshot {
    selections: readonly vscode.Selection[];
    version: number;
    pending?: {
        version: number;
        selections: vscode.Selection[];
        scheduled?: NodeJS.Immediate;
    };
}

export class CursorPreserver implements vscode.Disposable {
    private readonly documents = new Map<vscode.TextDocument, DocumentSnapshot>();
    private readonly editors = new Map<vscode.TextEditor, EditorSnapshot>();
    private readonly subscriptions: vscode.Disposable[];

    constructor(private readonly configuration: CompanionConfiguration) {
        this.subscriptions = [
            vscode.workspace.onDidChangeConfiguration(event => {
                if (event.affectsConfiguration('taskMasterCompanion')) {
                    this.refreshDocuments();
                }
            }),
            vscode.workspace.onDidOpenTextDocument(document => this.rememberDocument(document)),
            vscode.workspace.onDidCloseTextDocument(document => this.forgetDocument(document)),
            vscode.workspace.onDidChangeTextDocument(event => this.handleDocumentChange(event)),
            vscode.window.onDidChangeVisibleTextEditors(() => this.synchronizeEditors()),
            vscode.window.onDidChangeTextEditorSelection(event => this.handleSelectionChange(event)),
        ];
        this.refreshDocuments();
    }

    dispose(): void {
        this.subscriptions.forEach(subscription => subscription.dispose());
        this.editors.forEach(snapshot => cancelCorrection(snapshot));
        this.editors.clear();
        this.documents.clear();
    }

    private rememberDocument(document: vscode.TextDocument): void {
        if (this.configuration.select(document).kind === 'selected') {
            this.documents.set(document, {
                text: document.getText(), version: document.version, isDirty: document.isDirty,
            });
        }
    }

    private refreshDocuments(): void {
        this.editors.forEach(snapshot => cancelCorrection(snapshot));
        this.editors.clear();
        this.documents.clear();
        vscode.workspace.textDocuments.forEach(document => this.rememberDocument(document));
        this.synchronizeEditors();
    }

    private forgetDocument(document: vscode.TextDocument): void {
        this.documents.delete(document);
        for (const [editor, snapshot] of this.editors) {
            if (editor.document === document) {
                cancelCorrection(snapshot);
                this.editors.delete(editor);
            }
        }
    }

    private synchronizeEditors(): void {
        const visibleEditors = vscode.window.visibleTextEditors;
        for (const [editor, snapshot] of this.editors) {
            if (!visibleEditors.includes(editor)) {
                cancelCorrection(snapshot);
                this.editors.delete(editor);
            }
        }
        for (const editor of visibleEditors) {
            if (this.documents.has(editor.document) && !this.editors.has(editor)) {
                this.editors.set(editor, {
                    selections: [...editor.selections], version: editor.document.version,
                });
            }
        }
    }

    private handleDocumentChange(event: vscode.TextDocumentChangeEvent): void {
        const previous = this.documents.get(event.document);
        this.rememberDocument(event.document);
        if (!previous || event.contentChanges.length === 0) {
            return;
        }

        const isExternalReload = !previous.isDirty && !event.document.isDirty && event.reason === undefined;
        let mapper: PositionMapper | undefined;
        if (isExternalReload) {
            mapper = new PositionMapper(previous.text, event.document.getText());
        }
        for (const [editor, snapshot] of this.editors) {
            if (editor.document !== event.document) {
                continue;
            }
            cancelCorrection(snapshot);
            if (mapper && snapshot.version === previous.version) {
                const selections = snapshot.selections.map(selection => mapper.mapSelection(selection));
                snapshot.selections = selections;
                snapshot.pending = { version: event.document.version, selections };
                this.scheduleCorrection(editor, snapshot);
            } else {
                snapshot.selections = [...editor.selections];
            }
            snapshot.version = event.document.version;
        }
    }

    private handleSelectionChange(event: vscode.TextEditorSelectionChangeEvent): void {
        const snapshot = this.editors.get(event.textEditor);
        if (!snapshot) {
            return;
        }
        if (snapshot.pending && !equalSelections(event.selections, snapshot.pending.selections)) {
            if (event.kind === undefined && event.textEditor.document.version === snapshot.pending.version) {
                // VS Code sends its automatic selection adjustment after the content event.
                this.scheduleCorrection(event.textEditor, snapshot);
                return;
            }
        }

        cancelCorrection(snapshot);
        snapshot.selections = [...event.selections];
        snapshot.version = event.textEditor.document.version;
    }

    private scheduleCorrection(editor: vscode.TextEditor, snapshot: EditorSnapshot): void {
        const pending = snapshot.pending;
        if (!pending) {
            return;
        }
        if (pending.scheduled) {
            clearImmediate(pending.scheduled);
        }
        pending.scheduled = setImmediate(() => {
            pending.scheduled = undefined;
            if (snapshot.pending !== pending || editor.document.version !== pending.version
                || editor.document.isDirty || editor.document.isClosed
                || !vscode.window.visibleTextEditors.includes(editor)) {
                cancelCorrection(snapshot);
                return;
            }
            editor.selections = pending.selections;
        });
    }
}

function cancelCorrection(snapshot: EditorSnapshot): void {
    if (snapshot.pending?.scheduled) {
        clearImmediate(snapshot.pending.scheduled);
    }
    snapshot.pending = undefined;
}

function equalSelections(left: readonly vscode.Selection[], right: readonly vscode.Selection[]): boolean {
    return left.length === right.length && left.every((selection, index) =>
        selection.anchor.isEqual(right[index].anchor) && selection.active.isEqual(right[index].active));
}
