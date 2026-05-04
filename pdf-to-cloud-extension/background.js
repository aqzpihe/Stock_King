// background.js
importScripts('pdf-lib.min.js');

const CLIENT_ID = '498474105649-jamstlc17t7hke44ch97ov3b4u7nvln3.apps.googleusercontent.com';
const REDIRECT_URI = chrome.identity.getRedirectURL(); 
const SCOPES = 'https://www.googleapis.com/auth/drive';

// 用來快取 PDF，避免重複下載
let cachedPdf = { url: '', buffer: null };

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'saveToDrive') {
    savePdfToDrive(request.url, request.folderId, request.startPage, request.endPage)
      .then(() => sendResponse({ success: true }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true; 
  } else if (request.action === 'getFolders') {
    getFoldersFromDrive()
      .then(folders => sendResponse({ folders }))
      .catch(err => sendResponse({ error: err.message }));
    return true;
  }
});

async function authenticateWithGoogle() {
  return new Promise((resolve, reject) => {
    const authUrl = `https://accounts.google.com/o/oauth2/auth?client_id=${CLIENT_ID}&response_type=token&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&scope=${encodeURIComponent(SCOPES)}`;
    chrome.identity.launchWebAuthFlow({ url: authUrl, interactive: true }, (redirectUrl) => {
      if (chrome.runtime.lastError || !redirectUrl) {
        reject(new Error(chrome.runtime.lastError ? chrome.runtime.lastError.message : '驗證失敗'));
        return;
      }
      const urlParams = new URLSearchParams(new URL(redirectUrl.replace('#', '?')).search);
      const token = urlParams.get('access_token');
      if (token) resolve(token);
      else reject(new Error('未取得 Token'));
    });
  });
}

async function getFoldersFromDrive() {
  const token = await authenticateWithGoogle();
  const res = await fetch("https://www.googleapis.com/drive/v3/files?q=mimeType='application/vnd.google-apps.folder' and trashed=false&fields=files(id,name)&orderBy=name", {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (!res.ok) throw new Error("無法取得資料夾列表");
  const data = await res.json();
  return data.files || [];
}

async function fetchPdfBuffer(url) {
  // 檢查快取
  if (cachedPdf.url === url && cachedPdf.buffer) {
    return cachedPdf.buffer;
  }
  const response = await fetch(url);
  if (!response.ok) throw new Error(`無法獲取 PDF (HTTP: ${response.status})`);
  const buffer = await response.arrayBuffer();
  // 寫入快取
  cachedPdf = { url, buffer };
  return buffer;
}

async function processPdf(buffer, requestedStart, requestedEnd) {
  const pdfDoc = await PDFLib.PDFDocument.load(buffer);
  const totalPages = pdfDoc.getPageCount();

  // 核心邏輯：動態判斷起始與結束
  // 1. 如果 startPage 沒填 (null)，預設為 1
  const startPage = requestedStart || 1;
  // 2. 如果 endPage 沒填 (null)，預設為 PDF 的總頁數
  const endPage = requestedEnd || totalPages;

  // 若使用者選的範圍涵蓋全部，直接返回原始檔案以節省效能
  if (startPage <= 1 && endPage >= totalPages) {
    return new Blob([buffer], { type: 'application/pdf' });
  }

  const newPdf = await PDFLib.PDFDocument.create();
  const indices = [];
  
  // 計算要留下來的 index
  for (let i = startPage; i <= endPage; i++) {
    if (i >= 1 && i <= totalPages) {
      indices.push(i - 1); // PDF-lib 是 0-based index
    }
  }

  if (indices.length === 0) {
    return new Blob([buffer], { type: 'application/pdf' }); // 容錯機制
  }

  // 複製並寫入新 PDF
  const copiedPages = await newPdf.copyPages(pdfDoc, indices);
  copiedPages.forEach((page) => newPdf.addPage(page));

  const newPdfBytes = await newPdf.save();
  return new Blob([newPdfBytes], { type: 'application/pdf' });
}

async function savePdfToDrive(pdfUrl, folderId, startPage, endPage) {
  const token = await authenticateWithGoogle();
  
  // 透過快取機制獲取檔案
  const buffer = await fetchPdfBuffer(pdfUrl);
  let blob = await processPdf(buffer, startPage, endPage);

  const urlObj = new URL(pdfUrl);
  const filename = urlObj.pathname.split('/').pop() || `document_${Date.now()}.pdf`;

  const metadata = {
    name: filename,
    mimeType: 'application/pdf'
  };

  if (folderId && folderId !== 'root') {
    metadata.parents = [folderId];
  }

  const form = new FormData();
  form.append('metadata', new Blob([JSON.stringify(metadata)], { type: 'application/json' }));
  form.append('file', blob);

  const uploadRes = await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: form
  });

  if (!uploadRes.ok) {
    const errData = await uploadRes.text();
    throw new Error(`上傳失敗: ${errData}`);
  }

  return await uploadRes.json();
}
