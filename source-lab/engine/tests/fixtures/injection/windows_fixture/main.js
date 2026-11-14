const { app, BrowserWindow } = require('electron');
const path = require('path');

function createWindow() {
  const win = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  // WebView2 document created script injection pattern in win32 wrapper
  if (win.webContents.AddScriptToExecuteOnDocumentCreated) {
    win.webContents.AddScriptToExecuteOnDocumentCreated("console.log('wv2 injected');");
  }

  win.loadURL('https://example.test');
}

app.whenReady().then(createWindow);
