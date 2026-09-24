async function J(p){
  try{
    const r=await fetch(
      p+"?v="+Date.now(),
      {cache:"no-store"}
    );

    if(!r.ok){
      throw new Error("HTTP "+r.status);
    }

    return await r.json();
  }catch(e){
    console.error("JSON load failed:",p,e);
    return {};
  }
}
