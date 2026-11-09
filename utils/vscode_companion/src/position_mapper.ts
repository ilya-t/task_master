import { diffArrays, diffChars } from 'diff';
import * as vscode from 'vscode';

interface LineMapping {
    line: number;
    deleted: boolean;
    unchanged: boolean;
    replacement?: { start: number; end: number };
}

export class PositionMapper {
    private readonly oldLines: string[];
    private readonly newLines: string[];
    private readonly lineMappings: LineMapping[] = [];
    private readonly exactLines = new Map<string, number[]>();
    private readonly normalizedLines = new Map<string, number[]>();
    private readonly anchorLines = new Map<number, number>();

    constructor(oldText: string, newText: string) {
        this.oldLines = oldText.split(/\r?\n/);
        this.newLines = newText.split(/\r?\n/);
        this.newLines.forEach((line, index) => {
            appendLineIndex(this.exactLines, line, index);
            appendLineIndex(this.normalizedLines, normalizeTaskLine(line), index);
        });
        this.buildLineMappings();
        this.buildAnchorLines();
    }

    mapSelection(selection: vscode.Selection): vscode.Selection {
        return new vscode.Selection(this.mapPosition(selection.anchor), this.mapPosition(selection.active));
    }

    private mapPosition(position: vscode.Position): vscode.Position {
        const oldLine = Math.min(position.line, this.oldLines.length - 1);
        const mapping = this.lineMappings[oldLine];
        const matchingLine = this.findMatchingLine(oldLine);
        if (matchingLine !== undefined) {
            return new vscode.Position(matchingLine, mapCharacter(
                this.oldLines[oldLine], this.newLines[matchingLine], position.character,
            ));
        }
        if (mapping.deleted) {
            if (mapping.line < this.newLines.length) {
                return new vscode.Position(mapping.line, 0);
            }
            const lastLine = this.newLines.length - 1;
            return new vscode.Position(lastLine, this.newLines[lastLine].length);
        }

        return new vscode.Position(mapping.line, mapCharacter(
            this.oldLines[oldLine], this.newLines[mapping.line], position.character,
        ));
    }

    private findMatchingLine(oldLine: number): number | undefined {
        const text = this.oldLines[oldLine];
        if (text.trim() === '') {
            return this.findContextCandidate(oldLine, this.exactLines.get(text) ?? []);
        }
        if (this.lineMappings[oldLine].unchanged) {
            return this.lineMappings[oldLine].line;
        }

        const exactMatch = this.findCandidate(oldLine, this.exactLines.get(text) ?? [],
            this.oldLines.filter(line => line === text).length);
        if (exactMatch !== undefined) {
            return exactMatch;
        }
        const normalized = normalizeTaskLine(text);
        if (normalized === '') {
            return undefined;
        }
        const normalizedMatch = this.findCandidate(oldLine, this.normalizedLines.get(normalized) ?? [],
            this.oldLines.filter(line => normalizeTaskLine(line) === normalized).length);
        if (normalizedMatch !== undefined) {
            return normalizedMatch;
        }
        return this.findSimilarReplacement(oldLine, normalized);
    }

    private findSimilarReplacement(oldLine: number, text: string): number | undefined {
        const replacement = this.lineMappings[oldLine].replacement;
        if (!replacement || replacement.end - replacement.start < 2) {
            return undefined;
        }

        let bestLine: number | undefined;
        let bestScore = 0;
        let secondScore = 0;
        for (let line = replacement.start; line < replacement.end; line++) {
            const candidate = normalizeTaskLine(this.newLines[line]);
            let sharedLength = 0;
            let longestMatch = 0;
            for (const change of diffChars(text, candidate)) {
                if (!change.added && !change.removed) {
                    sharedLength += change.value.length;
                    longestMatch = Math.max(longestMatch, change.value.length);
                }
            }
            // A few scattered letters are not enough to identify the original task.
            if (longestMatch < 4) {
                continue;
            }
            const score = 2 * sharedLength / (text.length + candidate.length);
            if (score > bestScore) {
                secondScore = bestScore;
                bestScore = score;
                bestLine = line;
            } else {
                secondScore = Math.max(secondScore, score);
            }
        }
        // Require substantial overlap and a clear lead over other lines in this block.
        if (bestScore >= 0.6 && bestScore - secondScore >= 0.15) {
            return bestLine;
        }
        return undefined;
    }

    private findCandidate(oldLine: number, candidates: number[], oldOccurrences: number): number | undefined {
        if (candidates.length === 1 && oldOccurrences === 1) {
            return candidates[0];
        }

        const contextualMatch = this.findContextCandidate(oldLine, candidates);
        if (contextualMatch !== undefined) {
            return contextualMatch;
        }

        let lowerBound = -1;
        let upperBound = this.newLines.length;
        for (let index = oldLine - 1; index >= 0; index--) {
            if (this.lineMappings[index].unchanged) {
                lowerBound = this.lineMappings[index].line;
                break;
            }
        }
        for (let index = oldLine + 1; index < this.oldLines.length; index++) {
            if (this.lineMappings[index].unchanged) {
                upperBound = this.lineMappings[index].line;
                break;
            }
        }
        const nearbyCandidates = candidates.filter(line => line > lowerBound && line < upperBound);
        if (nearbyCandidates.length === 1) {
            return nearbyCandidates[0];
        }
        return undefined;
    }

    private findContextCandidate(oldLine: number, candidates: number[]): number | undefined {
        const matches = candidates.filter(line => this.hasMatchingNeighbor(oldLine, line, -1)
            || this.hasMatchingNeighbor(oldLine, line, 1));
        return matches.length === 1 ? matches[0] : undefined;
    }

    private hasMatchingNeighbor(oldLine: number, newLine: number, direction: number): boolean {
        let oldNeighbor = oldLine + direction;
        let newNeighbor = newLine + direction;
        while (oldNeighbor >= 0 && oldNeighbor < this.oldLines.length
            && newNeighbor >= 0 && newNeighbor < this.newLines.length) {
            const oldText = this.oldLines[oldNeighbor];
            const newText = this.newLines[newNeighbor];
            const normalized = normalizeTaskLine(oldText);
            if (oldText !== newText && (normalized === '' || normalized !== normalizeTaskLine(newText))) {
                return false;
            }
            const anchor = this.anchorLines.get(oldNeighbor);
            if (anchor !== undefined) {
                return anchor === newNeighbor;
            }
            oldNeighbor += direction;
            newNeighbor += direction;
        }
        return false;
    }

    private buildAnchorLines(): void {
        const oldExactLines = new Map<string, number[]>();
        const oldNormalizedLines = new Map<string, number[]>();
        this.oldLines.forEach((text, line) => {
            appendLineIndex(oldExactLines, text, line);
            appendLineIndex(oldNormalizedLines, normalizeTaskLine(text), line);
        });
        this.oldLines.forEach((text, line) => {
            const normalized = normalizeTaskLine(text);
            if (normalized === '') {
                return;
            }
            const mapping = this.lineMappings[line];
            const exact = this.exactLines.get(text);
            const normalizedMatches = this.normalizedLines.get(normalized);
            if (mapping.unchanged) {
                this.anchorLines.set(line, mapping.line);
            } else if (oldExactLines.get(text)?.length === 1 && exact?.length === 1) {
                this.anchorLines.set(line, exact[0]);
            } else if (oldNormalizedLines.get(normalized)?.length === 1 && normalizedMatches?.length === 1) {
                this.anchorLines.set(line, normalizedMatches[0]);
            }
        });
    }

    private buildLineMappings(): void {
        const changes = diffArrays(this.oldLines, this.newLines);
        let newLine = 0;
        let index = 0;
        while (index < changes.length) {
            const change = changes[index];
            if (!change.added && !change.removed) {
                for (let offset = 0; offset < change.value.length; offset++) {
                    this.lineMappings.push({ line: newLine + offset, deleted: false, unchanged: true });
                }
                newLine += change.value.length;
                index++;
                continue;
            }

            let removedCount = 0;
            let addedCount = 0;
            while (index < changes.length && (changes[index].added || changes[index].removed)) {
                if (changes[index].removed) {
                    removedCount += changes[index].value.length;
                } else {
                    addedCount += changes[index].value.length;
                }
                index++;
            }
            const replacement = { start: newLine, end: newLine + addedCount };
            for (let offset = 0; offset < removedCount; offset++) {
                const replacementOffset = Math.min(offset, Math.max(0, addedCount - 1));
                this.lineMappings.push({
                    line: newLine + replacementOffset,
                    deleted: addedCount === 0,
                    unchanged: false,
                    replacement,
                });
            }
            newLine += addedCount;
        }
    }
}

function appendLineIndex(index: Map<string, number[]>, text: string, line: number): void {
    const existing = index.get(text);
    if (existing) {
        existing.push(line);
    } else {
        index.set(text, [line]);
    }
}

function normalizeTaskLine(text: string): string {
    return text.trimStart().replace(/^(?:#{1,6}\s+|[-*+]\s+)?(?:\[[^\]\r\n]\]\s*)?/, '').trimEnd();
}

function mapCharacter(oldText: string, newText: string, character: number): number {
    const changes = diffChars(oldText, newText);
    const oldPosition = Math.min(character, oldText.length);
    let oldOffset = 0;
    let newOffset = 0;
    let index = 0;
    while (index < changes.length) {
        const change = changes[index];
        if (!change.added && !change.removed) {
            // value.length counts UTF-16 units, unlike diff's code-point count.
            if (oldPosition < oldOffset + change.value.length) {
                return newOffset + oldPosition - oldOffset;
            }
            oldOffset += change.value.length;
            newOffset += change.value.length;
            index++;
            continue;
        }

        let removedLength = 0;
        let addedLength = 0;
        while (index < changes.length && (changes[index].added || changes[index].removed)) {
            if (changes[index].removed) {
                removedLength += changes[index].value.length;
            } else {
                addedLength += changes[index].value.length;
            }
            index++;
        }
        if (oldPosition < oldOffset + removedLength) {
            return newOffset + Math.min(oldPosition - oldOffset, addedLength);
        }
        oldOffset += removedLength;
        newOffset += addedLength;
    }
    return newText.length;
}
