// Separate optical test scene; do not reuse v2 target coordinates.
const format=new URLSearchParams(location.search).get('format')==='portrait'?'portrait':'landscape';
document.documentElement.dataset.format=format;
window.OPENKEY_LAYOUTS.LOGICAL=format==='landscape'?{width:1920,height:1080}:{width:1080,height:1920};
window.OPENKEY_LAYOUTS.LAYOUTS.A.perPage=format==='landscape'?8:9;
window.OPENKEY_LAYOUTS.LAYOUTS.B.perPage=format==='landscape'?8:9;
