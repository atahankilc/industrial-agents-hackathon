// One camera frame as a JPEG data URL (at most 1280 px on the long side), for the Guide to read signs and room numbers.

export function grabFrame(video: HTMLVideoElement | null): string | undefined {
  if (!video || !video.videoWidth) return undefined
  const scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(video.videoWidth * scale)
  canvas.height = Math.round(video.videoHeight * scale)
  canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.82)
}
