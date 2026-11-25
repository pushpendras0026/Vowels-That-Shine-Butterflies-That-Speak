// AudioWorklet capture for the Live Voice Lab: batches 128-sample render quanta into 1024-sample
// chunks (mono mix of the input) and posts them to the main thread, which resamples to 16 kHz.
class LabCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.size = 1024;
    this.buf = new Float32Array(this.size);
    this.n = 0;
  }
  process(inputs) {
    const inp = inputs[0];
    if (inp && inp.length) {
      const a = inp[0], b = inp.length > 1 ? inp[1] : null;
      for (let i = 0; i < a.length; i++) {
        this.buf[this.n++] = b ? 0.5 * (a[i] + b[i]) : a[i];
        if (this.n === this.size) {
          this.port.postMessage(this.buf, [this.buf.buffer]);
          this.buf = new Float32Array(this.size);
          this.n = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("lab-capture", LabCapture);
