// let videoStream = null;
// let videoElement = null;

// export async function initWebcam() {
//   videoElement = document.createElement('video');
//   videoElement.autoplay = true;
//   videoElement.playsInline = true;
//   videoElement.style.display = 'none'; // Hide it if you don’t want to show preview
//   document.body.appendChild(videoElement);

//   try {
//     videoStream = await navigator.mediaDevices.getUserMedia({ video: true });
//     videoElement.srcObject = videoStream;
//     console.log("✅ Webcam initialized.");
//   } catch (err) {
//     console.error("❌ Webcam access denied:", err);
//   }
// }

// export async function takePictureAndUpload() {
//   if (!videoElement || !videoStream) {
//     console.warn("Webcam not initialized. Calling init...");
//     await initWebcam();
//   }

//   const canvas = document.createElement('canvas');
//   canvas.width = 320;
//   canvas.height = 240;
//   const ctx = canvas.getContext('2d');
//   ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);

//   canvas.toBlob(async (blob) => {
//     const formData = new FormData();
//     formData.append('file', blob, 'webcam.jpg');

//     const response = await fetch("http://localhost:8000/upload-image/", {
//       method: "POST",
//       body: formData,
//     });

//     const data = await response.json();
//     console.log("📤 Image uploaded:", data.message);
//   }, 'image/jpeg');
// }


let videoStream = null;
let videoElement = null;

export async function initWebcam() {
  // Create and configure hidden video element
  videoElement = document.createElement('video');
  videoElement.autoplay = true;
  videoElement.playsInline = true;
  videoElement.style.display = 'none'; // Hide video preview
  document.body.appendChild(videoElement);

  try {
    // Request access to webcam
    videoStream = await navigator.mediaDevices.getUserMedia({ video: true });
    videoElement.srcObject = videoStream;

    // Wait for metadata to load so we get correct resolution
    await new Promise(resolve => {
      videoElement.onloadedmetadata = () => resolve();
    });

    console.log(`✅ Webcam initialized at ${videoElement.videoWidth}x${videoElement.videoHeight}`);
  } catch (err) {
    console.error("❌ Webcam access denied:", err);
  }
}

export async function takePictureAndUpload() {
  if (!videoElement || !videoStream) {
    console.warn("Webcam not initialized. Initializing...");
    await initWebcam();
  }

  const width = videoElement.videoWidth;
  const height = videoElement.videoHeight;

  // Capture image at native resolution
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(videoElement, 0, 0, width, height);

  // Optional: show preview popup
  const previewImg = new Image();
  previewImg.src = canvas.toDataURL('image/jpeg');
  previewImg.style.position = 'fixed';
  previewImg.style.bottom = '10px';
  previewImg.style.right = '10px';
  previewImg.style.width = '160px';
  previewImg.style.border = '2px solid #fff';
  previewImg.style.boxShadow = '0 0 8px rgba(0,0,0,0.3)';
  document.body.appendChild(previewImg);
  setTimeout(() => previewImg.remove(), 3000); // Auto-remove after 3s

  // Convert to JPEG and upload
  canvas.toBlob(async (blob) => {
    const formData = new FormData();
    formData.append('file', blob, 'webcam.jpg');

    try {
      const response = await fetch("http://localhost:8000/upload-image/", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      console.log("📤 Image uploaded:", data.message);
    } catch (err) {
      console.error("❌ Upload failed:", err);
    }
  }, 'image/jpeg');
}

