const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');

class ProcessStub extends EventEmitter {
    constructor() {
        super();
        this.stdout = new PassThrough();
        this.stderr = new PassThrough();
        this.signals = [];
        this.pid = 123;
    }

    finish(code = 0, signal = null) {
        this.emit('exit', code, signal);
        this.emit('close', code, signal);
    }

    fail(error) {
        this.pid = undefined;
        this.emit('error', error);
    }

    kill(signal) {
        this.signals.push(signal);
        return true;
    }
}

module.exports = { ProcessStub };
