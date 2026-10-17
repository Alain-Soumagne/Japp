// Pont sécurisé entre l'interface Angular et Electron (contextIsolation + sandbox).
const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('native', {
  // chemin réel d'un fichier glissé-déposé (évite de copier une vidéo de plusieurs Go)
  getPath: (file) => webUtils.getPathForFile(file),
  // ouverture contrôlée : le processus principal n'accepte qu'une liste blanche d'adresses
  openExternal: (url) => ipcRenderer.send('open-external', String(url)),
});
