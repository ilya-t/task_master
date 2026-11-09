import { homedir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import * as vscode from 'vscode';

const section = 'taskMasterCompanion';

interface SelectedProfile {
    kind: 'selected';
    name: string;
    profile: Record<string, unknown>;
}

type ProfileSelection = SelectedProfile
    | { kind: 'disabled' | 'empty' | 'unmatched' }
    | { kind: 'error'; message: string };

export class CompanionConfiguration {
    select(document: vscode.TextDocument): ProfileSelection {
        if (document.uri.scheme !== 'file') {
            return { kind: 'disabled' };
        }
        try {
            const settings = vscode.workspace.getConfiguration(section, document.uri);
            const value = settings.get<unknown>('profiles', {});
            const profiles = requireObject(value, 'profiles');
            if (Object.keys(profiles).length === 0) {
                return { kind: 'empty' };
            }
            for (const [name, value] of Object.entries(profiles)) {
                const label = `Profile "${name}"`;
                const profile = requireObject(value, label);
                try {
                    requireKnownFields(profile, ['executable', 'files', 'params', 'verbose']);
                    const files = requireString(profile.files, 'files');
                    if (!files.trim()) {
                        throw new Error('files must be a nonblank string.');
                    }
                    if (this.matches(files, document)) {
                        return { kind: 'selected', name, profile };
                    }
                } catch (error) {
                    throw new Error(`${label}: ${errorMessage(error)}`);
                }
            }
            return { kind: 'unmatched' };
        } catch (error) {
            return { kind: 'error', message: errorMessage(error) };
        }
    }

    resolveLaunch(selected: SelectedProfile, document: vscode.TextDocument): { executable: string; args: string[] } {
        const executable = requireString(selected.profile.executable, 'executable');
        if (!executable.trim()) {
            throw new Error('executable must be a nonblank string.');
        }
        const verbose = selected.profile.verbose;
        if (verbose !== undefined && typeof verbose !== 'boolean') {
            throw new Error('verbose must be a boolean.');
        }
        const params = selected.profile.params === undefined ? {} : requireObject(selected.profile.params, 'params');
        requireKnownFields(params, [
            'archive', 'config', 'experimental-archived-links-processor',
            'reminders', 'executions-dir', 'memories-dir',
        ]);
        const args: string[] = [];
        for (const [name, value] of Object.entries(params)) {
            if (name === 'reminders') {
                if (typeof value !== 'boolean') {
                    throw new Error('params.reminders must be a boolean.');
                }
                if (value) {
                    args.push('--reminders');
                }
                continue;
            }
            const text = requireString(value, `params.${name}`);
            if (text !== '') {
                const argument = name === 'experimental-archived-links-processor'
                    ? text : this.resolvePath(text, document);
                args.push(`--${name}=${argument}`);
            }
        }
        args.push(document.uri.fsPath);
        const expanded = this.expandPath(executable, document);
        return {
            executable: expanded.includes('/') ? resolve(this.baseDirectory(document), expanded) : expanded,
            args,
        };
    }

    private matches(pattern: string, document: vscode.TextDocument): boolean {
        const expanded = this.expandPath(pattern, document);
        const selector = isAbsolute(expanded)
            ? expanded : new vscode.RelativePattern(this.baseDirectory(document), expanded);
        return vscode.languages.match({ scheme: 'file', pattern: selector }, document) > 0;
    }

    private resolvePath(value: string, document: vscode.TextDocument): string {
        return resolve(this.baseDirectory(document), this.expandPath(value, document));
    }

    private expandPath(value: string, document: vscode.TextDocument): string {
        let expanded = value;
        if (expanded.includes('${workspaceFolder}')) {
            const folder = vscode.workspace.getWorkspaceFolder(document.uri);
            if (!folder) {
                throw new Error('${workspaceFolder} requires a file inside a workspace folder.');
            }
            expanded = expanded.replaceAll('${workspaceFolder}', folder.uri.fsPath);
        }
        if (/\$\{[^}]*\}/.test(expanded)) {
            throw new Error('Only ${workspaceFolder} is supported in paths and file patterns.');
        }
        if (expanded === '~') {
            return homedir();
        }
        if (expanded.startsWith('~/')) {
            return join(homedir(), expanded.slice(2));
        }
        return expanded;
    }

    private baseDirectory(document: vscode.TextDocument): string {
        return vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath ?? dirname(document.uri.fsPath);
    }
}

function requireObject(value: unknown, label: string): Record<string, unknown> {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) {
        throw new Error(`${label} must be an object.`);
    }
    return value as Record<string, unknown>;
}

function requireKnownFields(value: Record<string, unknown>, allowed: string[]): void {
    for (const name of Object.keys(value)) {
        if (!allowed.includes(name)) {
            throw new Error(`Unknown field or parameter "${name}".`);
        }
    }
}

function requireString(value: unknown, name: string): string {
    if (typeof value !== 'string') {
        throw new Error(`${name} must be a string.`);
    }
    if (value.includes('\0')) {
        throw new Error(`${name} must not contain null characters.`);
    }
    return value;
}

function errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
}
