import React from 'react';

interface WhatsAppPreviewProps {
  businessName: string;
  templateBody: string;
  headerType?: string | null;
  headerContent?: string | null;
  footer?: string | null;
  buttons?: any | null;
}

export const WhatsAppPreview: React.FC<WhatsAppPreviewProps> = ({
  businessName,
  templateBody,
  headerType,
  headerContent,
  footer,
  buttons,
}) => {
  const replaceVars = (text: string) => {
    if (!text) return '';
    return text.replace(/\{\{name\}\}/g, businessName || '{{name}}');
  };

  const getMediaUrl = () => {
    if (!headerContent) return null;
    try {
      const data = JSON.parse(headerContent);
      if (data.source_type === 'upload' && data.media_id) {
        return `/api/v1/whatsapp/media/${data.media_id}`;
      }
      if (data.source_type === 'url' && data.url) {
        return data.url;
      }
    } catch (e) {
      // If it's not JSON, assume it's a raw URL (backward compatibility)
      return headerContent;
    }
    return null;
  };
  
  const resolvedMediaUrl = getMediaUrl();

  return (
    <div className="w-[300px] h-[550px] bg-[#efeae2] rounded-3xl border-8 border-slate-900 shadow-2xl relative overflow-hidden flex flex-col mx-auto">
      {/* Phone Header */}
      <div className="bg-[#008069] text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <span className="material-symbols-outlined text-[20px]">arrow_back</span>
        <div className="w-8 h-8 bg-[#dfe5e7] rounded-full flex items-center justify-center text-[#54656f]">
          <span className="material-symbols-outlined text-[18px]">business</span>
        </div>
        <div className="flex-1 overflow-hidden">
          <div className="font-semibold text-sm truncate">Sharma Enterprises</div>
          <div className="text-[10px] text-white/80">+91 9911844469</div>
        </div>
      </div>

      {/* Message Area */}
      <div className="flex-1 p-3 overflow-y-auto bg-[url('https://web.whatsapp.com/img/bg-chat-tile-dark_a4be512e7195b6b733d9110b408f075d.png')] bg-repeat bg-[length:400px]">
        {/* Message Bubble */}
        <div className="bg-white rounded-lg rounded-tl-none shadow-sm p-1.5 w-[90%] text-[#111b21] text-[13px] relative">
          
          {/* Header */}
          {headerType === 'IMAGE' && resolvedMediaUrl && (
            <div className="w-full h-32 bg-[#dfe5e7] rounded-t-md mb-2 overflow-hidden flex items-center justify-center relative">
               <img src={resolvedMediaUrl} alt="Header" className="w-full h-full object-cover" />
            </div>
          )}
          {headerType === 'VIDEO' && resolvedMediaUrl && (
            <div className="w-full h-32 bg-[#2a3942] rounded-t-md mb-2 flex items-center justify-center relative">
               <span className="material-symbols-outlined text-white text-3xl">play_circle</span>
            </div>
          )}

          {/* Body */}
          <div className="px-1.5 whitespace-pre-wrap font-sans">
            {replaceVars(templateBody)}
          </div>

          {/* Footer */}
          {footer && (
            <div className="px-1.5 mt-2 text-[11px] text-[#667781] font-sans">
              {footer}
            </div>
          )}
          
          <div className="text-right text-[10px] text-[#8696a0] mt-1 mr-1">
            {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
        </div>

        {/* Buttons */}
        {buttons && Array.isArray(buttons) && buttons.length > 0 && (
          <div className="w-[90%] mt-1 flex flex-col gap-1">
            {buttons.map((btn, idx) => (
              <div key={idx} className="bg-white rounded-lg shadow-sm py-2 text-center text-[#00a884] font-medium text-[13px] border border-slate-100 flex items-center justify-center gap-1.5 cursor-pointer hover:bg-slate-50 transition-colors">
                {btn.type === 'URL' && <span className="material-symbols-outlined text-[16px]">open_in_new</span>}
                {btn.type === 'PHONE_NUMBER' && <span className="material-symbols-outlined text-[16px]">call</span>}
                {btn.type === 'QUICK_REPLY' && <span className="material-symbols-outlined text-[16px]">reply</span>}
                <span>{btn.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
