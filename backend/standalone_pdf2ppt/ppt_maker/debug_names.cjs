const sizeOf = require('image-size');
const fs = require('fs');
fs.readdirSync('../参考/images').forEach(f => {
    const d = sizeOf('../参考/images/'+f);
    console.log(f, d.width, 'x', d.height, (d.width/d.height).toFixed(2));
});
