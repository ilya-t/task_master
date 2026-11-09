import * as vscode from 'vscode';
import { TaskMasterCompanion } from './task_master_companion';
import { CursorPreserver } from './cursor_preserver';
import { CompanionConfiguration } from './companion_configuration';

let companion: TaskMasterCompanion | undefined;
let cursorPreserver: CursorPreserver | undefined;

export function activate(context: vscode.ExtensionContext): void {
    if (!vscode.workspace.isTrusted || (process.platform !== 'darwin' && process.platform !== 'linux')) {
        return;
    }

    const configuration = new CompanionConfiguration();
    companion = new TaskMasterCompanion(configuration);
    cursorPreserver = new CursorPreserver(configuration);
    context.subscriptions.push(companion, cursorPreserver);
}

export function deactivate(): void {
    companion?.dispose();
    companion = undefined;
    cursorPreserver?.dispose();
    cursorPreserver = undefined;
}
