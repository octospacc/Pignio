const { readFileSync } = require('fs')
const { stdout, argv } = require('process')
const { createCanvas, loadImage } = require('canvas')
const { drawText } = require('canvas-txt')

const scale = 2
const width = 500 * scale
const padding = 48 * scale
const drawOptions = {
  x: 0, // (width / 4),
  y: 0, // padding,
  width, // : (width / 2),
  fontSize: 32 * scale,
  font: '',
  // vAlign: 'top',
  // debug: true,
}

const background = argv.length === 3 ? argv[2] : null
const text = readFileSync(0 /* stdin */, 'utf8')

if (background) {
  loadImage(background).then(image => stdout.write(textToPng(image)))
} else {
  stdout.write(textToPng())
}

function newCanvas(height=0) {
  const canvas = createCanvas(width, height)
  const ctx = Object.assign(canvas.getContext('2d'), { textDrawingMode: "glyph" })
  return [canvas, ctx]
}

function textToPng(image) {
  const [testCanvas, testCtx] = newCanvas()
  let { height } = drawText(testCtx, text, { ...drawOptions, height: 1 })

  if (image) {
    height = width * (image.height / image.width)
  } else {
    height += (padding * 2)
  }

  const [canvas, ctx] = newCanvas(height)

  if (image) {
    ctx.drawImage(image, 0, 0, width, height)
  }

  ctx.fillStyle = 'black'
  drawText(ctx, text, { ...drawOptions, height })

  ctx.fillStyle = 'blue'
  drawText(ctx, text, { ...drawOptions, height, x: 1 * scale, y: 1 * scale })

  ctx.fillStyle = '#1e87f0'
  drawText(ctx, text, { ...drawOptions, height, x: 2 * scale, y: 2 * scale })

  return canvas.toBuffer('image/png')
}
