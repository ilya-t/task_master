import { ChildProcess, spawn } from 'node:child_process';
import { dirname } from 'node:path';
import * as vscode from 'vscode';
import { CompanionConfiguration } from './companion_configuration';

export class TaskMasterCompanion implements vscode.Disposable {
    private readonly output = vscode.window.createOutputChannel('Task Master Companion');
    private readonly saveSubscription: vscode.Disposable;
    private readonly configurationSubscription: vscode.Disposable;
    private readonly reportedConfigurationErrors = new Set<string>();
    private promptedForConfiguration = false;
    private activeProcess: ChildProcess | undefined;
    private isRunning = false;
    private isDisposed = false;

    constructor(private readonly configuration: CompanionConfiguration) {
        this.saveSubscription = vscode.workspace.onDidSaveTextDocument(document => {
            if (document.uri.scheme !== 'file' || this.isDisposed || !vscode.workspace.isTrusted) {
                return;
            }
            this.handleSave(document);
        });
        this.configurationSubscription = vscode.workspace.onDidChangeConfiguration(event => {
            if (event.affectsConfiguration('taskMasterCompanion')) {
                this.reportedConfigurationErrors.clear();
            }
        });
    }

    dispose(): void {
        if (this.isDisposed) {
            return;
        }

        this.isDisposed = true;
        this.saveSubscription.dispose();
        this.configurationSubscription.dispose();
        this.activeProcess?.kill('SIGTERM');
        this.output.dispose();
    }

    private handleSave(document: vscode.TextDocument): void {
        const selected = this.configuration.select(document);
        if (selected.kind === 'empty') {
            if (!this.promptedForConfiguration) {
                this.promptedForConfiguration = true;
                void vscode.window.showInformationMessage(
                    'Configure Task Master Companion profiles to enable processing.', 'Open Settings',
                ).then(action => this.handleNotificationAction(action));
            }
            return;
        }
        if (selected.kind === 'error') {
            this.reportConfigurationError(selected.message);
            return;
        }
        if (selected.kind !== 'selected') {
            return;
        }
        const filePath = document.uri.fsPath;
        if (this.isRunning) {
            this.output.appendLine(`Skipped while Task Master is running: ${filePath}`);
            return;
        }

        let launch: { executable: string; args: string[] };
        try {
            launch = this.configuration.resolveLaunch(selected, document);
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            this.reportConfigurationError(`Profile "${selected.name}": ${message}`);
            return;
        }
        if (selected.profile.verbose === true) {
            this.output.show(true);
        }
        this.processFile(filePath, selected.name, launch.executable, launch.args);
    }

    private processFile(filePath: string, profileName: string, executable: string, args: string[]): void {
        this.isRunning = true;
        this.output.appendLine(`Running Task Master: ${filePath} (profile: ${profileName})`);
        try {
            const child = spawn(executable, args, {
                cwd: dirname(filePath),
                shell: false,
                stdio: ['ignore', 'pipe', 'pipe'],
            });
            this.activeProcess = child;
            let processError: Error | undefined;
            child.stdout.setEncoding('utf8');
            child.stderr.setEncoding('utf8');
            child.stdout.on('data', (data: string) => {
                if (!this.isDisposed) {
                    this.output.append(data);
                }
            });
            child.stderr.on('data', (data: string) => {
                if (!this.isDisposed) {
                    this.output.append(data);
                }
            });
            child.on('error', (error: Error) => {
                processError = error;
                if (child.pid === undefined) {
                    // Failed spawns have no exit event.
                    this.releaseProcess(child);
                }
                this.reportError(`Task Master failed for ${filePath}: ${error.message}`);
            });
            // Descendant shells can keep stdout/stderr open after Task Master exits.
            child.once('exit', (code, signal) => {
                this.releaseProcess(child);
                if (this.isDisposed) {
                    return;
                }

                this.output.appendLine(`\nFinished Task Master: ${filePath} (code: ${code}, signal: ${signal ?? 'none'})`);
                if (code !== 0 && !processError) {
                    this.reportError(`Task Master failed for ${filePath} (code: ${code}, signal: ${signal ?? 'none'}).`);
                }
            });
        } catch (error) {
            this.isRunning = false;
            const message = error instanceof Error ? error.message : String(error);
            this.reportError(`Cannot start Task Master for ${filePath}: ${message}`);
        }
    }

    private releaseProcess(child: ChildProcess): void {
        if (this.activeProcess === child) {
            this.activeProcess = undefined;
            this.isRunning = false;
        }
    }

    private reportError(message: string): void {
        if (this.isDisposed) {
            return;
        }

        this.output.appendLine(message);
        void vscode.window.showErrorMessage(message, 'Open Log').then(action => this.handleNotificationAction(action));
    }

    private reportConfigurationError(message: string): void {
        if (this.reportedConfigurationErrors.has(message)) {
            return;
        }
        this.reportedConfigurationErrors.add(message);
        const description = `Invalid Task Master Companion configuration: ${message}`;
        this.output.appendLine(description);
        void vscode.window.showErrorMessage(description, 'Open Settings', 'Open Log')
            .then(action => this.handleNotificationAction(action));
    }

    private handleNotificationAction(action: string | undefined): void {
        if (this.isDisposed) {
            return;
        }
        if (action === 'Open Log') {
            this.output.show(true);
        } else if (action === 'Open Settings') {
            void vscode.commands.executeCommand('workbench.action.openSettings', '@ext:ilya-t.task-master-companion');
        }
    }
}
