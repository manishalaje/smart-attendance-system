// ---------- GLOBAL ----------
let pieChart, lineChart, barChart;
let busy = false;
let lastMarked = null;

let video;
let canvasOverlay;
let status;

// ---------- INIT PIE ----------
function initChart(){
    const ctx = document.getElementById("pie");
    if(!ctx) return;

    pieChart = new Chart(ctx, {
        type: "pie",
        data: {
            labels: ["AI","Math","DBMS"],
            datasets: [{
                data: [0,0,0],
                backgroundColor: ["#3b82f6","#22c55e","#f59e0b"]
            }]
        },
        options: {
            responsive:true,
            maintainAspectRatio:false
        }
    });
}

// ---------- LINE ----------
function initLineChart(){
    const ctx = document.getElementById("lineChart");
    if(!ctx) return;

    lineChart = new Chart(ctx, {
        type:"line",
        data:{ labels:[], datasets:[{ label:"Trend", data:[], borderColor:"#3b82f6" }] }
    });
}

// ---------- BAR ----------
function initBarChart(){
    const ctx = document.getElementById("barChart");
    if(!ctx) return;

    barChart = new Chart(ctx, {
        type:"bar",
        data:{
            labels:["AI","Math","DBMS"],
            datasets:[{ data:[0,0,0] }]
        }
    });
}

// ---------- UPDATE CHART ----------
function updateChart(){
    fetch("/live_data")
    .then(r=>r.json())
    .then(d=>{
        if(!d.subjects) return;

        pieChart.data.labels = d.subjects;
        pieChart.data.datasets[0].data = d.counts;
        pieChart.update();

        if(barChart){
            barChart.data.labels = d.subjects;
            barChart.data.datasets[0].data = d.counts;
            barChart.update();
        }
    })
    .catch(()=>{});
}

// ---------- LINE ----------
function updateLineChart(){
    fetch("/live_data")
    .then(r=>r.json())
    .then(d=>{
        if(!lineChart) return;

        lineChart.data.labels = d.subjects || [];
        lineChart.data.datasets[0].data = d.counts || [];
        lineChart.update();
    })
    .catch(()=>{});
}

// ---------- CAPTURE ----------
function getImage(){
    const c = document.createElement("canvas");
    c.width = video.videoWidth;
    c.height = video.videoHeight;
    c.getContext("2d").drawImage(video,0,0);
    return c.toDataURL("image/jpeg");
}

// ---------- DRAW BOX ----------
function drawBox(box, name){
    if(!canvasOverlay || !video) return;

    canvasOverlay.width = video.videoWidth;
    canvasOverlay.height = video.videoHeight;

    const ctx = canvasOverlay.getContext("2d");
    ctx.clearRect(0,0,canvasOverlay.width,canvasOverlay.height);

    if(!box) return;

    let [top, right, bottom, left] = box;

    ctx.strokeStyle="#22c55e";
    ctx.lineWidth=3;
    ctx.strokeRect(left,top,right-left,bottom-top);

    if(name){
        ctx.fillStyle="#22c55e";
        ctx.fillText(name,left,top-5);
    }
}

// ---------- REGISTER ----------
function register(){
    const name = document.getElementById("name").value;

    if(!name){
        status.innerText="Enter name";
        return;
    }

    fetch("/register_image",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
            name:name,
            image:getImage()
        })
    })
    .then(r=>r.json())
    .then(d=>{
        status.innerText=d.message;
    })
    .catch(()=>status.innerText="Error");
}

// ---------- MARK ----------
function mark(){
    fetch("/recognize_image",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
            image:getImage(),
            subject:document.getElementById("subject").value
        })
    })
    .then(r=>r.json())
    .then(d=>{
        status.innerText=d.message+" "+(d.name||"");

        if(d.box){
            drawBox(d.box,d.name);
        }else{
            drawBox(null,null);
        }
    })
    .catch(()=>status.innerText="Error");
}

// ---------- AUTO DETECT ----------
function autoDetect(){
    if(busy || !video || !video.videoWidth) return;

    busy=true;

    fetch("/recognize_image",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
            image:getImage(),
            subject:document.getElementById("subject").value
        })
    })
    .then(r=>r.json())
    .then(d=>{

        if(d.success){
            if(lastMarked!==d.name){
                status.innerText="✅ "+d.name;
                lastMarked=d.name;
            }
        }else{
            status.innerText="❌ "+d.message;
        }

        drawBox(d.box || null, d.name || null);

        busy=false;
    })
    .catch(()=>busy=false);
}

// ---------- INIT ----------
document.addEventListener("DOMContentLoaded", function(){

    video = document.getElementById("video");
    canvasOverlay = document.getElementById("overlay");
    status = document.getElementById("status");

    // CAMERA
    if(video){
        navigator.mediaDevices.getUserMedia({video:true})
        .then(stream=>video.srcObject=stream)
        .catch(()=>status.innerText="Camera blocked");
    }

    initChart();
    initLineChart();
    initBarChart();

    // 🔥 SAFE INTERVALS
    setInterval(updateChart,3000);
    setInterval(updateLineChart,4000);
    setInterval(autoDetect,2000); // slower = safer
});