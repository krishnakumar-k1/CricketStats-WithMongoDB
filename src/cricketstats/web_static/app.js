const $ = (id) => document.getElementById(id);
const demos = {
  Test: ["What is Sachin Tendulkar's Test batting average?", "How many Test hundreds did Sachin Tendulkar score?", "Who was the first Indian to score centuries in both innings of a Test?"],
  IPL: ["Who won the IPL Orange Cap in 2023?", "Who won the IPL Purple Cap in 2023?", "Who has scored the most IPL runs?", "Who has hit the most sixes in IPL?"]
};
let demoIndex = {Test:0, IPL:0};
function clearAnswer(){$("resultState").classList.add("hidden");$("loading").classList.add("hidden");$("emptyState").classList.remove("hidden")}
function setQuestion(value){$("question").value=value;clearAnswer()}
function renderSuggestions(){const mode=$("format").value;$("suggestions").innerHTML=demos[mode].slice(0,3).map(q=>`<button type="button">${q}</button>`).join("");document.querySelectorAll(".suggestions button").forEach(b=>b.onclick=()=>setQuestion(b.textContent));clearAnswer()}
$("format").onchange=renderSuggestions;renderSuggestions();
$("loadDemo").onclick=()=>{const mode=$("format").value;setQuestion(demos[mode][demoIndex[mode]++%demos[mode].length])};
$("detailsButton").onclick=()=>$("queryDetails").classList.toggle("hidden");
$("askButton").onclick=async()=>{const question=$("question").value.trim();if(!question){$("question").focus();return}const button=$("askButton");button.disabled=true;$("emptyState").classList.add("hidden");$("resultState").classList.add("hidden");$("loading").classList.remove("hidden");try{const response=await fetch("/api/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({format:$("format").value,question})});const data=await response.json();if(!response.ok)throw new Error(data.error||"Query failed");$("answerText").textContent=data.answer;$("sourceText").textContent=`${data.plan.collection} · ${data.rows.length} result${data.rows.length===1?"":"s"}`;$("queryDetails").textContent=JSON.stringify(data.plan,null,2);$("queryDetails").classList.add("hidden");$("resultState").classList.remove("hidden")}catch(error){$("answerText").textContent=error.message;$("sourceText").textContent="Request could not be completed";$("resultState").classList.remove("hidden")}finally{$("loading").classList.add("hidden");button.disabled=false}};
$("question").addEventListener("keydown",e=>{if((e.metaKey||e.ctrlKey)&&e.key==="Enter")$("askButton").click()});
$("question").addEventListener("input",clearAnswer);
