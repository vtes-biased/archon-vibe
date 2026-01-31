

export const index = 0;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/_layout.svelte.js')).default;
export const universal = {
  "ssr": false,
  "prerender": true
};
export const universal_id = "src/routes/+layout.ts";
export const imports = ["_app/immutable/nodes/0.BcSsBavu.js","_app/immutable/chunks/D_UohZrd.js","_app/immutable/chunks/BtUdmAei.js","_app/immutable/chunks/CNlSSih3.js","_app/immutable/chunks/DMeojxED.js","_app/immutable/chunks/C1Vdx43v.js","_app/immutable/chunks/clKjiprP.js","_app/immutable/chunks/CCbajElR.js","_app/immutable/chunks/CUMSltq5.js","_app/immutable/chunks/DgThuZgT.js","_app/immutable/chunks/Cg_6fdU5.js","_app/immutable/chunks/C3TxV-85.js","_app/immutable/chunks/DIFp9cza.js","_app/immutable/chunks/BEdTVS4X.js","_app/immutable/chunks/Ct5FWWRu.js"];
export const stylesheets = ["_app/immutable/assets/0.DX0k25Td.css"];
export const fonts = [];
