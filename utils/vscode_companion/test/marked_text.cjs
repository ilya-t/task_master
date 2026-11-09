const assert = require('node:assert/strict');

function parseCaret(markedText) {
    const offset = markedText.indexOf('|');
    assert.ok(offset >= 0 && offset === markedText.lastIndexOf('|'), 'Expected exactly one cursor marker');
    const precedingLines = markedText.slice(0, offset).split(/\r?\n/);
    return {
        text: markedText.slice(0, offset) + markedText.slice(offset + 1),
        position: { line: precedingLines.length - 1, character: precedingLines.at(-1).length },
    };
}

function markCaret(text, position) {
    const lines = text.split('\n');
    assert.ok(position.line >= 0 && position.line < lines.length, 'Cursor line must be inside the document');
    const line = lines[position.line];
    assert.ok(position.character >= 0 && position.character <= line.replace(/\r$/, '').length,
        'Cursor column must be inside the line');
    lines[position.line] = line.slice(0, position.character) + '|' + line.slice(position.character);
    return lines.join('\n');
}

module.exports = { parseCaret, markCaret };
