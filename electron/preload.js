// Pont sécurisé entre l'interface Angular et Electron (contextIsolation + sandbox).
const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('native', {
  // chemin réel d'un fichier glissé-déposé (évite de copier une vidéo de plusieurs Go)
  getPath: (file) => webUtils.getPathForFile(file),
  // ouverture contrôlée : le processus principal n'accepte qu'une liste blanche d'adresses
  openExternal: (url) => ipcRenderer.send('open-external', String(url)),
  // mises à jour : vérification, téléchargement vérifié, rien n'est installé automatiquement
  update: {
    get: () => ipcRenderer.invoke('update:get'),
    check: () => ipcRenderer.invoke('update:check'),
    download: () => ipcRenderer.invoke('update:download'),
    reveal: () => ipcRenderer.invoke('update:reveal'),
    dismiss: () => ipcRenderer.invoke('update:dismiss'),
    setEnabled: (on) => ipcRenderer.invoke('update:set-enabled', !!on),
    onState: (cb) => {
      const h = (_e, s) => cb(s);
      ipcRenderer.on('update:state', h);
      return () => ipcRenderer.removeListener('update:state', h);
    },
  },
});
