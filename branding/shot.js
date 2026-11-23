const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch();
for (const [f,w,h] of [['profile',800,800],['card',1080,1920]]){
 const p=await b.newPage({viewport:{width:w,height:h},deviceScaleFactor:1});
 await p.goto('file://'+process.cwd()+'/'+f+'.html'); await p.waitForTimeout(500);
 await p.screenshot({path:f+'.png'});}
await b.close();})();
