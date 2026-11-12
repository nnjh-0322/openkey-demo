// OpenKey Live 손 인식 워커. 05-data/tools/finger-demo/static/hand-worker.js 를 복사해
// 검출 기준값을 init 메시지로 바꿀 수 있게 했다(원본·03-software 워커는 그대로).
// 모델·wasm은 03-software/vendor 를 /sw/ 경로로 읽는다(실행 중 외부 CDN 호출 없음).
let detector = null;
self.onmessage = async ({ data: m }) => {
  try {
    if (m.type === "init") {
      const { FilesetResolver, HandLandmarker } = await import(m.bundle);
      const files = await FilesetResolver.forVisionTasks(m.wasm, true);
      const det = Number.isFinite(m.det) ? m.det : 0.35;
      detector = await HandLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: m.model, delegate: "CPU" }, runningMode: "VIDEO", numHands: 2,
        minHandDetectionConfidence: det, minHandPresenceConfidence: Math.max(0.3, det + 0.05), minTrackingConfidence: 0.5,
      });
      self.postMessage({ type: "ready", det });
      return;
    }
    if (m.type === "frame") {
      if (!detector) throw Error("모델 준비 전");
      const start = performance.now();
      const result = detector.detectForVideo(m.bitmap, m.at);
      m.bitmap.close();
      self.postMessage({ type: "result", token: m.token, at: m.at, landmarks: result.landmarks, handedness: result.handedness, modelMs: performance.now() - start });
    }
  } catch (error) {
    m.bitmap?.close();
    self.postMessage({ type: "error", token: m.token, message: String(error.message || error) });
  }
};
