const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('veriify', {
  checkOllama: () => ipcRenderer.invoke('check-ollama'),
  checkModel: () => ipcRenderer.invoke('check-model'),
  getPlatform: () => ipcRenderer.invoke('get-platform'),
  installOllama: () => ipcRenderer.invoke('install-ollama'),
  pullModel: (callback) => {
    ipcRenderer.on('pull-progress', (_, progress) => callback(progress));
    return ipcRenderer.invoke('pull-model');
  },
  finishSetup: () => ipcRenderer.invoke('finish-setup')
});
