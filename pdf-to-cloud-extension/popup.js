document.addEventListener('DOMContentLoaded', async () => {
  const folderSelect = document.getElementById('folderSelect');
  
  // 取得資料夾列表
  chrome.runtime.sendMessage({ action: 'getFolders' }, (response) => {
    folderSelect.innerHTML = '<option value="root">我的雲端硬碟 (根目錄)</option>'; // 重置
    if (response && response.folders) {
      response.folders.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f.id;
        opt.innerText = f.name;
        folderSelect.appendChild(opt);
      });
      // 載入先前儲存的資料夾選擇
      chrome.storage.local.get(['lastFolderId'], (result) => {
        if (result.lastFolderId) {
          folderSelect.value = result.lastFolderId;
        }
      });
    } else {
      folderSelect.innerHTML = '<option value="root">無法載入資料夾，將存於根目錄</option>';
    }
  });

  // 當使用者切換資料夾時，即時儲存偏好
  folderSelect.addEventListener('change', () => {
    chrome.storage.local.set({ lastFolderId: folderSelect.value });
  });
});

document.getElementById('saveBtn').addEventListener('click', async () => {
  const statusDiv = document.getElementById('status');
  statusDiv.innerText = "處理中 (讀取、擷取與上傳)...";
  statusDiv.style.color = "#0078D7";

  const folderId = document.getElementById('folderSelect').value;
  const startPageStr = document.getElementById('startPage').value;
  const endPageStr = document.getElementById('endPage').value;

  // 若空白則傳 null 給背景腳本動態判斷
  const startPage = startPageStr ? parseInt(startPageStr) : null;
  const endPage = endPageStr ? parseInt(endPageStr) : null;

  // 點擊儲存時再確保儲存一次資料夾偏好
  chrome.storage.local.set({ lastFolderId: folderId });

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  if (!tab.url.toLowerCase().includes('.pdf')) {
    statusDiv.innerText = "⚠️ 當前頁面可能不是 PDF 檔案";
    statusDiv.style.color = "#D83B01";
  }

  // 將資料傳送給 background.js 執行任務
  chrome.runtime.sendMessage({ 
    action: 'saveToDrive', 
    url: tab.url,
    folderId: folderId,
    startPage: startPage,
    endPage: endPage
  }, (response) => {
    if (chrome.runtime.lastError) {
      statusDiv.innerText = "❌ 發生錯誤: " + chrome.runtime.lastError.message;
      statusDiv.style.color = "red";
      return;
    }

    if (response && response.success) {
      statusDiv.innerText = "✅ 成功上傳到雲端！";
      statusDiv.style.color = "green";
    } else {
      statusDiv.innerText = "❌ 上傳失敗: " + (response ? response.error : "未知錯誤");
      statusDiv.style.color = "red";
    }
  });
});
