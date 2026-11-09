const assert = require('node:assert/strict');
const { test } = require('node:test');
const { ExtensionHarness } = require('./harness.cjs');
const { Position, Selection } = require('./editor_environment.cjs');
const { parseCaret, markCaret } = require('./marked_text.cjs');

const overview = `# group-a
- item-01
- item-02
- item-03
- item-04
- item-05
- item-06
- item-07
- item-08
- item-09
- item-10
- item-11
- item-12
- item-13
- item-14
- item-15
- item-16
- item-17
- item-18
- item-19
- item-20
- item-21
- item-22
- item-23
- item-24
- item-25
- item-26
- item-27
- item-28
- item-29
`;

test('an empty nested checkbox follows its moved item past an existing overview', async t => {
    const remaining = `# [-] group-b
- [ ] item-d
    - [ ] 
- [ ] 
`;
    await assertCursor(t, {
        before: `item-a
- [!] item-b
    - [ ] item-c
    - [ ] |
- [ ] 

` + overview + remaining,
        after: overview + `# [-] group-c 
item-a
- [!] item-b
    - [ ] item-c
    - [ ] |
- [ ] 

` + remaining,
    });
});

test('a generated summary link does not win over the corrected original text', async t => {
    await assertCursor(t, {
        before: `sample value a|bx

# group-b
value-b`,
        after: overview + `- [sample value aby](#item)
# [-] group-c
sample value a|by

# group-b
value-b`,
    });
});

test('a changed checkbox keeps the cursor in the item text', async t => {
    await assertCursor(t, {
        before: `- [ ] it|em
next`,
        after: `- [x] it|em
next`,
    });
});

test('a new prefix moves the cursor with the existing text', async t => {
    await assertCursor(t, {
        before: `|item
next`,
        after: `- [ ] |item
next`,
    });
});

test('a shorter replacement clamps the cursor to its end', async t => {
    await assertCursor(t, {
        before: `abc|def
next`,
        after: `XY|
next`,
    });
});

test('deleting lines above moves the cursor with its item', async t => {
    await assertCursor(t, {
        before: `intro
head
- [ ] |item
end`,
        after: `- [ ] |item
end`,
    });
});

test('a moved item with a changed checkbox keeps its cursor', async t => {
    await assertCursor(t, {
        before: `- [ ] it|em
one
two
three`,
        after: `one
two
three
- [x] it|em`,
    });
});

test('neighboring lines distinguish duplicate item titles', async t => {
    await assertCursor(t, {
        before: `# A
- [ ] |item
# B
- [x] item`,
        after: `# A
new
- [x] |item
# B
- [x] item`,
    });
});

test('ambiguous item titles use the local replacement position', async t => {
    await assertCursor(t, {
        before: `head
- [ ] |item
end`,
        after: `head
- [x] |item
- [x] item
end`,
    });
});

test('a deleted item leaves the cursor at the start of the next line', async t => {
    await assertCursor(t, {
        before: `head
- [ ] it|em
end`,
        after: `head
|end`,
    });
});

test('an empty file has a valid cursor at its beginning', async t => {
    await assertCursor(t, {
        before: 'it|em',
        after: '|',
    });
});

test('UTF-16 columns include both units of inserted emoji', async t => {
    await assertCursor(t, {
        before: '🚀 |item',
        after: '🌟 🚀 |item',
    });
});

test('multiple cursors and backwards selections retain their order and direction', async t => {
    // Arrange
    const harness = new ExtensionHarness(t);
    const editor = openEditor(harness, `alph|a
beta`);
    harness.editorEnvironment.moveSelections(editor, [
        selectionBetween(`alpha
bet|a`, `a|lpha
beta`),
        selectionAt(`alph|a
beta`),
    ], 3);
    // Act
    harness.editorEnvironment.changeDocument(editor.document, `intro
alpha
beta`);
    await new Promise(resolve => setImmediate(resolve));
    // Assert
    assert.deepEqual(markSelections(editor), [
        {
            anchor: `intro
alpha
bet|a`,
            active: `intro
a|lpha
beta`,
        },
        {
            anchor: `intro
alph|a
beta`,
            active: `intro
alph|a
beta`,
        },
    ]);
});

for (const { name, inputs } of [
    { name: 'typing does not restore the previous cursor', inputs: { isDirty: true } },
    { name: 'undo to saved content does not restore the previous cursor', inputs: { reason: 1 } },
]) {
    test(name, async t => {
        const harness = new ExtensionHarness(t);
        const editor = openEditor(harness, 'it|em');
        harness.editorEnvironment.changeDocument(editor.document, 'item-b', inputs);
        harness.editorEnvironment.moveSelections(editor, [selectionAt('item-b|')], 1);
        await new Promise(resolve => setImmediate(resolve));
        assertCursorAt(editor, 'item-b|');
        assert.equal(editor.selectionWrites, 0);
    });
}

test('a user selection cancels pending restoration', async t => {
    const harness = new ExtensionHarness(t);
    const editor = openEditor(harness, `it|em
end`);
    harness.editorEnvironment.changeDocument(editor.document, `prefix-a item
end`);
    harness.editorEnvironment.moveSelections(editor, [selectionAt(`prefix-a item
|end`)], 1);
    await new Promise(resolve => setImmediate(resolve));
    assertCursorAt(editor, `prefix-a item
|end`);
    assert.equal(editor.selectionWrites, 0);
});

test('successive reloads map the pending position through every version', async t => {
    const harness = new ExtensionHarness(t);
    const editor = openEditor(harness, `it|em
end`);
    harness.editorEnvironment.changeDocument(editor.document, `intro
item
end`);
    harness.editorEnvironment.moveSelections(editor, [selectionAt(`intro
item
|end`)], undefined);
    harness.editorEnvironment.changeDocument(editor.document, `intro
- [ ] item
end`);
    await new Promise(resolve => setImmediate(resolve));
    assertCursorAt(editor, `intro
- [ ] it|em
end`);
});

test('two visible editors of one document preserve their own positions', async t => {
    const harness = new ExtensionHarness(t);
    const first = openEditor(harness, `it|em
end`);
    const second = harness.editorEnvironment.showDocument(first.document, [selectionAt(`item
e|nd`)]);
    harness.editorEnvironment.changeDocument(first.document, `intro
item
end`);
    await new Promise(resolve => setImmediate(resolve));
    assertCursorAt(first, `intro
it|em
end`);
    assertCursorAt(second, `intro
item
e|nd`);
});

test('closing a document cancels pending restoration', async t => {
    const harness = new ExtensionHarness(t);
    const editor = openEditor(harness, 'it|em');
    harness.editorEnvironment.changeDocument(editor.document, 'prefix-a item');
    harness.editorEnvironment.closeDocument(editor.document);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(editor.selectionWrites, 0);
});

test('deactivation cancels pending restoration and removes editor subscriptions', async t => {
    const harness = new ExtensionHarness(t);
    const editor = openEditor(harness, 'it|em');
    harness.editorEnvironment.changeDocument(editor.document, 'prefix-a item');
    harness.extension.deactivate();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(editor.selectionWrites, 0);
    assert.equal(harness.editorEnvironment.events.eventNames().length, 0);
});

test('other files are not subject to cursor restoration', async t => {
    const harness = new ExtensionHarness(t);
    const editor = openEditor(harness, 'it|em', `${harness.directory}/other.md`);
    harness.editorEnvironment.changeDocument(editor.document, 'prefix-a item');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(editor.selectionWrites, 0);
});

test('a dirty document becoming clean does not restore its stale position', async t => {
    const harness = new ExtensionHarness(t);
    const editor = openEditor(harness, 'it|em');
    harness.editorEnvironment.changeDocument(editor.document, 'item-b', { isDirty: true });
    harness.editorEnvironment.changeDocument(editor.document, 'replacement');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(editor.selectionWrites, 0);
});

test('a document version change before correction cancels the stale position', async t => {
    const harness = new ExtensionHarness(t);
    const editor = openEditor(harness, 'it|em');
    harness.editorEnvironment.changeDocument(editor.document, 'prefix-a item');
    harness.editorEnvironment.changeDocument(editor.document, 'prefix-a item!', { isDirty: true });
    harness.editorEnvironment.moveSelections(editor, [selectionAt('prefix-a item!|')], 1);
    await new Promise(resolve => setImmediate(resolve));
    assertCursorAt(editor, 'prefix-a item!|');
    assert.equal(editor.selectionWrites, 0);
});

test('excluding an open file cancels pending restoration and stops future corrections', async t => {
    // Arrange
    const harness = new ExtensionHarness(t);
    const editor = openEditor(harness, 'it|em');
    harness.editorEnvironment.changeDocument(editor.document, 'prefix-a item');
    // Act
    harness.setConfiguration({ profiles: { B: { files: '**/other.md', executable: 'run' } } });
    await new Promise(resolve => setImmediate(resolve));
    harness.editorEnvironment.changeDocument(editor.document, 'prefix-b item');
    harness.editorEnvironment.moveSelections(editor, [selectionAt('|prefix-b item')], undefined);
    await new Promise(resolve => setImmediate(resolve));
    // Assert
    assertCursorAt(editor, '|prefix-b item');
    assert.equal(editor.selectionWrites, 0);
});

test('including an already open file begins preserving its current cursor', async t => {
    // Arrange
    const harness = new ExtensionHarness(t, { configuration: {} });
    const editor = openEditor(harness, 'it|em', '/workspace-a/input.md');
    // Act
    harness.setConfiguration({ profiles: { A: { files: '**/input.md', executable: 'run' } } });
    harness.editorEnvironment.changeDocument(editor.document, 'prefix-a item');
    harness.editorEnvironment.moveSelections(editor, [selectionAt('|prefix-a item')], undefined);
    await new Promise(resolve => setImmediate(resolve));
    // Assert
    assertCursorAt(editor, 'prefix-a it|em');
    assert.equal(editor.document.isDirty, false);
});

async function assertCursor(t, { before, after, configuration, filePath }) {
    const harness = new ExtensionHarness(t, { configuration });
    const editor = openEditor(harness, before, filePath);
    const updatedText = parseCaret(after).text;
    harness.editorEnvironment.changeDocument(editor.document, updatedText);
    harness.editorEnvironment.moveSelections(editor, [selectionAt('|' + updatedText)], undefined);
    await new Promise(resolve => setImmediate(resolve));
    assertCursorAt(editor, after);
    assert.equal(editor.document.isDirty, false);
    assert.deepEqual(harness.records(), []);
}

function openEditor(harness, markedText, filePath = harness.filePath) {
    return harness.editorEnvironment.openEditor(filePath, parseCaret(markedText).text, [selectionAt(markedText)]);
}

function selectionAt(markedText) {
    const { position } = parseCaret(markedText);
    const cursor = new Position(position.line, position.character);
    return new Selection(cursor, cursor);
}

function selectionBetween(anchorText, activeText) {
    const anchor = parseCaret(anchorText);
    const active = parseCaret(activeText);
    assert.equal(anchor.text, active.text, 'Selection endpoints must refer to the same document');
    return new Selection(
        new Position(anchor.position.line, anchor.position.character),
        new Position(active.position.line, active.position.character),
    );
}

function assertCursorAt(editor, expected) {
    assert.deepEqual(markSelections(editor), [{ anchor: expected, active: expected }]);
}

function markSelections(editor) {
    return editor.selections.map(selection => ({
        anchor: markCaret(editor.document.getText(), selection.anchor),
        active: markCaret(editor.document.getText(), selection.active),
    }));
}
