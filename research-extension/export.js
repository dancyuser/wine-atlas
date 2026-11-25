'use strict';

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.target !== 'research-export' || sender.id !== chrome.runtime.id) return false;
  const json = new Blob([message.payload], {type: 'application/json;charset=utf-8'});
  respond({url: URL.createObjectURL(json)});
  return false;
});
