"""
What Eko says about the Banking Outlet, from Eko's Creator Pack (October
2026): the confirmed FAQ answers, who we speak to, what every message should
carry, and the words we do not use.

Two uses:
  * the onboarding bot answers a person's question from the FAQ, in their
    language (match, reply), instead of only handing it to the team;
  * the template agents read agent_section() before writing, for personas,
    hooks and facts to build new templates from.

Only the Banking Outlet track for now: the bot's flow (12th pass, ₹5 lakh)
is the Outlet's, so Touchpoint-only answers and personas are left out. The
team chose to keep SBI's name and logo, rupee figures and "franchise" as
they are, so only the Creator Pack's word rules that do not conflict with
those are applied (AVOID).
"""
import re
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# The FAQ, confirmed by Eko. Each answer in Hinglish (the pack's own wording),
# English, Hindi, Gujarati and Punjabi; keys are the words that ask it.
# ---------------------------------------------------------------------------

FAQ: List[dict] = [
    {
        "id": "job", "question": "Kya yeh bank ki naukri hai?",
        "keys": ["naukri", "nokri", "job", "bank ki naukri", "sarkari", "government job", "नौकरी", "નોકરી", "ਨੌਕਰੀ", "vacancy", "bharti", "भर्ती"],
        "answer": {
            "hinglish": "Nahi. Yeh aapka apna business hai. Aap Eko ke saath hamare partner bank ki banking sevayein apne ilaake mein dete hain.",
            "en": "No. This is your own business. With Eko, you offer our partner bank's banking services in your area.",
            "hi": "नहीं। यह आपका अपना बिज़नेस है। आप Eko के साथ हमारे पार्टनर बैंक की बैंकिंग सेवाएँ अपने इलाके में देते हैं।",
            "gu": "ના. આ તમારો પોતાનો બિઝનેસ છે. તમે Eko સાથે અમારી પાર્ટનર બેંકની બેંકિંગ સેવાઓ તમારા વિસ્તારમાં આપો છો.",
            "pa": "ਨਹੀਂ। ਇਹ ਤੁਹਾਡਾ ਆਪਣਾ ਕਾਰੋਬਾਰ ਹੈ। ਤੁਸੀਂ Eko ਨਾਲ ਸਾਡੇ ਪਾਰਟਨਰ ਬੈਂਕ ਦੀਆਂ ਬੈਂਕਿੰਗ ਸੇਵਾਵਾਂ ਆਪਣੇ ਇਲਾਕੇ ਵਿੱਚ ਦਿੰਦੇ ਹੋ।",
        },
    },
    {
        "id": "real", "question": "Kya yeh asli hai? Eko kaun hai?",
        "keys": ["asli", "real", "fake", "fraud", "froud", "genuine", "eko kaun", "who is eko", "kaun hai", "company kaun", "भरोसा", "असली", "फर्जी", "धोखा", "અસલી", "છેતરપિંડી", "ਅਸਲੀ", "ਧੋਖਾ"],
        "answer": {
            "hinglish": "Eko Bharat Ventures Private Limited 2009 se ek National Business Correspondent hai.",
            "en": "Eko Bharat Ventures Private Limited has been a National Business Correspondent since 2009.",
            "hi": "Eko Bharat Ventures Private Limited 2009 से एक नेशनल बिज़नेस कॉरेस्पॉन्डेंट है।",
            "gu": "Eko Bharat Ventures Private Limited 2009થી નેશનલ બિઝનેસ કૉરસ્પોન્ડન્ટ છે.",
            "pa": "Eko Bharat Ventures Private Limited 2009 ਤੋਂ ਇੱਕ ਨੈਸ਼ਨਲ ਬਿਜ਼ਨਸ ਕੋਰੈਸਪੋਂਡੈਂਟ ਹੈ।",
        },
    },
    {
        "id": "fees", "question": "Apply karne ki fees?",
        "keys": ["fees", "fee", "registration", "apply karne", "apply ka", "allotment", "paise dene", "charge apply", "फीस", "शुल्क", "ફી", "ਫੀਸ"],
        "answer": {
            "hinglish": "Apply karna free hai. Allotment ke naam par kisi ko paise na dein.",
            "en": "Applying is free. Do not pay anyone in the name of an allotment.",
            "hi": "अप्लाई करना फ्री है। अलॉटमेंट के नाम पर किसी को पैसे न दें।",
            "gu": "અરજી કરવી મફત છે. ફાળવણીના નામે કોઈને પૈસા ન આપો.",
            "pa": "ਅਪਲਾਈ ਕਰਨਾ ਮੁਫ਼ਤ ਹੈ। ਅਲਾਟਮੈਂਟ ਦੇ ਨਾਮ 'ਤੇ ਕਿਸੇ ਨੂੰ ਪੈਸੇ ਨਾ ਦਿਓ।",
        },
    },
    {
        "id": "outlet_touchpoint", "question": "Banking Outlet aur Touchpoint mein kya fark hai?",
        "keys": ["touchpoint", "touch point", "outlet", "fark", "difference", "अंतर", "फर्क", "ફરક", "ਫਰਕ"],
        "answer": {
            "hinglish": "Banking Outlet poori banking seva deta hai, tay ghante aur zyada investment. Touchpoint mein paisa jama, nikasi aur transfer, flexible ghante aur kam investment.",
            "en": "A Banking Outlet offers full banking services, with fixed hours and a larger investment. A Touchpoint offers cash deposit, withdrawal and transfers, with flexible hours and a smaller investment.",
            "hi": "बैंकिंग आउटलेट पूरी बैंकिंग सेवा देता है, तय घंटे और ज़्यादा निवेश। टचपॉइंट में पैसा जमा, निकासी और ट्रांसफर, लचीले घंटे और कम निवेश।",
            "gu": "બેંકિંગ આઉટલેટ સંપૂર્ણ બેંકિંગ સેવા આપે છે, નક્કી કલાકો અને વધુ રોકાણ. ટચપોઈન્ટમાં પૈસા જમા, ઉપાડ અને ટ્રાન્સફર, લવચીક કલાકો અને ઓછું રોકાણ.",
            "pa": "ਬੈਂਕਿੰਗ ਆਊਟਲੈੱਟ ਪੂਰੀ ਬੈਂਕਿੰਗ ਸੇਵਾ ਦਿੰਦਾ ਹੈ, ਤੈਅ ਘੰਟੇ ਅਤੇ ਵੱਧ ਨਿਵੇਸ਼। ਟੱਚਪੁਆਇੰਟ ਵਿੱਚ ਪੈਸੇ ਜਮ੍ਹਾਂ, ਕਢਵਾਉਣਾ ਅਤੇ ਟ੍ਰਾਂਸਫਰ, ਲਚਕੀਲੇ ਘੰਟੇ ਅਤੇ ਘੱਟ ਨਿਵੇਸ਼।",
        },
    },
    {
        "id": "promise", "question": "Eko ka vaada kya hai?",
        "keys": ["vaada", "vada", "wada", "promise", "eko kya karega", "eko kya karta", "support", "madad karega", "वादा", "વચન", "ਵਾਅਦਾ"],
        "answer": {
            "hinglish": "Aapki month-on-month growth. Iske liye Eko har process chalata hai: training, roz ka saath, yojana campaigns, certificate mein madad, devices aur compliance.",
            "en": "Your month-on-month growth. For that, Eko runs every process: training, daily support, scheme campaigns, help with certification, devices and compliance.",
            "hi": "आपकी महीने-दर-महीने ग्रोथ। इसके लिए Eko हर प्रोसेस चलाता है: ट्रेनिंग, रोज़ का साथ, योजना कैंपेन, सर्टिफिकेट में मदद, डिवाइस और कंप्लायंस।",
            "gu": "તમારો મહિને-દર-મહિને વિકાસ. એ માટે Eko દરેક પ્રક્રિયા ચલાવે છે: તાલીમ, રોજનો સાથ, યોજના ઝુંબેશ, પ્રમાણપત્રમાં મદદ, ડિવાઇસ અને નિયમપાલન.",
            "pa": "ਤੁਹਾਡਾ ਮਹੀਨਾ-ਦਰ-ਮਹੀਨਾ ਵਾਧਾ। ਇਸ ਲਈ Eko ਹਰ ਪ੍ਰਕਿਰਿਆ ਚਲਾਉਂਦਾ ਹੈ: ਟ੍ਰੇਨਿੰਗ, ਰੋਜ਼ ਦਾ ਸਾਥ, ਯੋਜਨਾ ਮੁਹਿੰਮਾਂ, ਸਰਟੀਫਿਕੇਟ ਵਿੱਚ ਮਦਦ, ਡਿਵਾਈਸ ਅਤੇ ਕੰਪਲਾਇੰਸ।",
        },
    },
    {
        "id": "investment", "question": "Kitna invest karna hoga?",
        "keys": ["invest", "investment", "nivesh", "kitna paisa", "kitne paise", "lagat", "kharcha", "5 lakh", "paanch lakh", "निवेश", "लागत", "खर्चा", "રોકાણ", "ખર્ચ", "ਨਿਵੇਸ਼", "ਖਰਚਾ"],
        "answer": {
            "hinglish": "INR 5 lakh tak, location aur setup par nirbhar.",
            "en": "Up to ₹5 lakh, depending on the location and the setup.",
            "hi": "₹5 लाख तक, लोकेशन और सेटअप पर निर्भर।",
            "gu": "₹5 લાખ સુધી, સ્થાન અને સેટઅપ પર આધારિત.",
            "pa": "₹5 ਲੱਖ ਤੱਕ, ਲੋਕੇਸ਼ਨ ਅਤੇ ਸੈੱਟਅੱਪ 'ਤੇ ਨਿਰਭਰ।",
        },
    },
    {
        "id": "devices", "question": "Kaun se devices chahiye?",
        "keys": ["device", "devices", "machine", "laptop", "computer", "biometric", "micro atm", "printer", "gps", "dongle", "मशीन", "डिवाइस", "मशीनें", "મશીન", "ડિવાઇસ", "ਮਸ਼ੀਨ", "ਡਿਵਾਈਸ"],
        "answer": {
            "hinglish": "Laptop ya tab, biometric device, micro ATM, passbook printer, GPS dongle. Eko lagata aur sikhata hai.",
            "en": "A laptop or tablet, a biometric device, a micro ATM, a passbook printer and a GPS dongle. Eko installs them and teaches you to use them.",
            "hi": "लैपटॉप या टैब, बायोमेट्रिक डिवाइस, माइक्रो ATM, पासबुक प्रिंटर, GPS डोंगल। Eko लगाता और सिखाता है।",
            "gu": "લેપટોપ કે ટેબ, બાયોમેટ્રિક ડિવાઇસ, માઇક્રો ATM, પાસબુક પ્રિન્ટર, GPS ડોંગલ. Eko લગાવે છે અને શીખવે છે.",
            "pa": "ਲੈਪਟਾਪ ਜਾਂ ਟੈਬ, ਬਾਇਓਮੈਟ੍ਰਿਕ ਡਿਵਾਈਸ, ਮਾਈਕ੍ਰੋ ATM, ਪਾਸਬੁੱਕ ਪ੍ਰਿੰਟਰ, GPS ਡੋਂਗਲ। Eko ਲਗਾਉਂਦਾ ਅਤੇ ਸਿਖਾਉਂਦਾ ਹੈ।",
        },
    },
    {
        "id": "with_shop", "question": "Kya dukaan ke saath chala sakte hain?",
        "keys": ["dukaan ke saath", "dukan ke sath", "shop ke saath", "dukaan mein", "alag jagah", "jagah", "space", "premises", "timing", "ghante", "दुकान", "जगह", "दुकान के साथ", "દુકાન", "જગ્યા", "ਦੁਕਾਨ", "ਜਗ੍ਹਾ"],
        "answer": {
            "hinglish": "Banking Outlet ke liye alag jagah aur tay ghante chahiye. Touchpoint flexible hai.",
            "en": "A Banking Outlet needs its own space and fixed hours. A Touchpoint is more flexible.",
            "hi": "बैंकिंग आउटलेट के लिए अलग जगह और तय घंटे चाहिए। टचपॉइंट लचीला है।",
            "gu": "બેંકિંગ આઉટલેટ માટે અલગ જગ્યા અને નક્કી કલાકો જોઈએ. ટચપોઈન્ટ લવચીક છે.",
            "pa": "ਬੈਂਕਿੰਗ ਆਊਟਲੈੱਟ ਲਈ ਵੱਖਰੀ ਜਗ੍ਹਾ ਅਤੇ ਤੈਅ ਘੰਟੇ ਚਾਹੀਦੇ ਹਨ। ਟੱਚਪੁਆਇੰਟ ਲਚਕੀਲਾ ਹੈ।",
        },
    },
    {
        "id": "training", "question": "Training aur certificate?",
        "keys": ["training", "certificate", "iibf", "exam", "sikhayenge", "course", "ट्रेनिंग", "सर्टिफिकेट", "प्रशिक्षण", "તાલીમ", "સર્ટિફિકેટ", "ਟ੍ਰੇਨਿੰਗ", "ਸਰਟੀਫਿਕੇਟ"],
        "answer": {
            "hinglish": "Eko training deta hai. Banking Outlet operator ko IIBF ka advanced certificate lena hota hai.",
            "en": "Eko gives the training. A Banking Outlet operator has to get the IIBF advanced certificate.",
            "hi": "Eko ट्रेनिंग देता है। बैंकिंग आउटलेट ऑपरेटर को IIBF का एडवांस्ड सर्टिफिकेट लेना होता है।",
            "gu": "Eko તાલીમ આપે છે. બેંકિંગ આઉટલેટ ઓપરેટરે IIBFનું એડવાન્સ્ડ સર્ટિફિકેટ લેવું પડે છે.",
            "pa": "Eko ਟ੍ਰੇਨਿੰਗ ਦਿੰਦਾ ਹੈ। ਬੈਂਕਿੰਗ ਆਊਟਲੈੱਟ ਆਪਰੇਟਰ ਨੂੰ IIBF ਦਾ ਐਡਵਾਂਸਡ ਸਰਟੀਫਿਕੇਟ ਲੈਣਾ ਪੈਂਦਾ ਹੈ।",
        },
    },
    {
        "id": "family", "question": "Kya family member saath kaam kar sakta hai?",
        "keys": ["family", "parivaar", "parivar", "beta", "beti", "wife", "patni", "pati", "bhai", "sub-ko", "sub ko", "परिवार", "बेटा", "पत्नी", "પરિવાર", "દીકરો", "ਪਰਿਵਾਰ", "ਪੁੱਤਰ"],
        "answer": {
            "hinglish": "Haan, aage chalkar sub-KO jod sakte hain.",
            "en": "Yes, later on you can add them as a sub-KO.",
            "hi": "हाँ, आगे चलकर सब-KO जोड़ सकते हैं।",
            "gu": "હા, આગળ જતાં સબ-KO તરીકે ઉમેરી શકો છો.",
            "pa": "ਹਾਂ, ਅੱਗੇ ਚੱਲ ਕੇ ਸਬ-KO ਜੋੜ ਸਕਦੇ ਹੋ।",
        },
    },
    {
        "id": "earning_lines", "question": "Banking Outlet mein kamaai ke zyada raaste kyun?",
        "keys": ["kaun si seva", "kaun kaun si", "services", "seva", "sevayein", "kya kya", "loan", "rd", "fd", "ekyc", "debit card", "सेवा", "सेवाएँ", "सुविधा", "સેવા", "ਸੇਵਾ"],
        "answer": {
            "hinglish": "Banking Outlet mein khate, yojanayein, RD, FD, loan collection, loan leads, eKYC, debit card jaisi zyada sevayein hain, aur har seva ka apna commission hai.",
            "en": "A Banking Outlet offers more services: accounts, government schemes, RD, FD, loan collection, loan leads, eKYC, debit cards and more, and each service earns its own commission.",
            "hi": "बैंकिंग आउटलेट में खाते, योजनाएँ, RD, FD, लोन कलेक्शन, लोन लीड, eKYC, डेबिट कार्ड जैसी ज़्यादा सेवाएँ हैं, और हर सेवा का अपना कमीशन है।",
            "gu": "બેંકિંગ આઉટલેટમાં ખાતાં, યોજનાઓ, RD, FD, લોન કલેક્શન, લોન લીડ, eKYC, ડેબિટ કાર્ડ જેવી વધુ સેવાઓ છે, અને દરેક સેવાનું પોતાનું કમિશન છે.",
            "pa": "ਬੈਂਕਿੰਗ ਆਊਟਲੈੱਟ ਵਿੱਚ ਖਾਤੇ, ਯੋਜਨਾਵਾਂ, RD, FD, ਲੋਨ ਕਲੈਕਸ਼ਨ, ਲੋਨ ਲੀਡ, eKYC, ਡੈਬਿਟ ਕਾਰਡ ਵਰਗੀਆਂ ਵੱਧ ਸੇਵਾਵਾਂ ਹਨ, ਅਤੇ ਹਰ ਸੇਵਾ ਦਾ ਆਪਣਾ ਕਮਿਸ਼ਨ ਹੈ।",
        },
    },
    {
        "id": "earnings", "question": "Kamaai kitni hogi?",
        "keys": ["kamaai", "kamai", "kamayi", "kamaenge", "kamayenge", "earning", "earnings", "income", "commission", "profit", "munafa", "kitna milega", "कमाई", "आमदनी", "कमीशन", "मुनाफा", "કમાણી", "આવક", "કમિશન", "ਕਮਾਈ", "ਆਮਦਨ", "ਕਮਿਸ਼ਨ"],
        "answer": {
            "hinglish": "Har seva aur har enrolment par commission, aur goals poore karne par incentive. Kamaai mehnat aur location par nirbhar hai. Koi guaranteed income nahi.",
            "en": "Commission on every service and every enrolment, and incentives for meeting goals. Earnings depend on your effort and location. There is no guaranteed income.",
            "hi": "हर सेवा और हर एनरोलमेंट पर कमीशन, और लक्ष्य पूरे करने पर इंसेंटिव। कमाई मेहनत और लोकेशन पर निर्भर है। कोई गारंटीड आमदनी नहीं।",
            "gu": "દરેક સેવા અને દરેક નોંધણી પર કમિશન, અને લક્ષ્ય પૂરા કરવા પર ઇન્સેન્ટિવ. કમાણી મહેનત અને સ્થાન પર આધારિત છે. કોઈ ગેરંટીવાળી આવક નથી.",
            "pa": "ਹਰ ਸੇਵਾ ਅਤੇ ਹਰ ਐਨਰੋਲਮੈਂਟ 'ਤੇ ਕਮਿਸ਼ਨ, ਅਤੇ ਟੀਚੇ ਪੂਰੇ ਕਰਨ 'ਤੇ ਇੰਸੈਂਟਿਵ। ਕਮਾਈ ਮਿਹਨਤ ਅਤੇ ਲੋਕੇਸ਼ਨ 'ਤੇ ਨਿਰਭਰ ਹੈ। ਕੋਈ ਗਾਰੰਟੀਸ਼ੁਦਾ ਆਮਦਨ ਨਹੀਂ।",
        },
    },
    {
        "id": "salary", "question": "Kya fixed salary milegi?",
        "keys": ["salary", "selery", "fixed salary", "tankhwah", "vetan", "pagar", "mahina fix", "fixed", "सैलरी", "वेतन", "तनख्वाह", "પગાર", "ਤਨਖਾਹ"],
        "answer": {
            "hinglish": "Nahi. Yeh naukri nahi, business hai. Kamaai commission aur goal-based incentive se hoti hai.",
            "en": "No. This is not a job, it is a business. Earnings come from commission and goal-based incentives.",
            "hi": "नहीं। यह नौकरी नहीं, बिज़नेस है। कमाई कमीशन और लक्ष्य-आधारित इंसेंटिव से होती है।",
            "gu": "ના. આ નોકરી નહીં, બિઝનેસ છે. કમાણી કમિશન અને લક્ષ્ય-આધારિત ઇન્સેન્ટિવથી થાય છે.",
            "pa": "ਨਹੀਂ। ਇਹ ਨੌਕਰੀ ਨਹੀਂ, ਕਾਰੋਬਾਰ ਹੈ। ਕਮਾਈ ਕਮਿਸ਼ਨ ਅਤੇ ਟੀਚਾ-ਅਧਾਰਿਤ ਇੰਸੈਂਟਿਵ ਤੋਂ ਹੁੰਦੀ ਹੈ।",
        },
    },
    {
        "id": "women", "question": "Mahila operators ke liye kuch alag hai?",
        "keys": ["mahila", "women", "woman", "ladies", "lady", "aurat", "female", "girl", "महिला", "औरत", "महिलाओं", "મહિલા", "સ્ત્રી", "ਔਰਤ", "ਮਹਿਲਾ"],
        "answer": {
            "hinglish": "Haan, mahila operators ko kul commission par ek atirikt incentive milta hai, ek seema tak.",
            "en": "Yes, women operators get an extra incentive on their total commission, up to a limit.",
            "hi": "हाँ, महिला ऑपरेटरों को कुल कमीशन पर एक अतिरिक्त इंसेंटिव मिलता है, एक सीमा तक।",
            "gu": "હા, મહિલા ઓપરેટરોને કુલ કમિશન પર એક વધારાનો ઇન્સેન્ટિવ મળે છે, એક મર્યાદા સુધી.",
            "pa": "ਹਾਂ, ਮਹਿਲਾ ਆਪਰੇਟਰਾਂ ਨੂੰ ਕੁੱਲ ਕਮਿਸ਼ਨ 'ਤੇ ਇੱਕ ਵਾਧੂ ਇੰਸੈਂਟਿਵ ਮਿਲਦਾ ਹੈ, ਇੱਕ ਹੱਦ ਤੱਕ।",
        },
    },
    {
        "id": "penalty", "question": "Koi penalty bhi hai?",
        "keys": ["penalty", "penality", "jurmana", "fine", "dand", "band rahe to", "जुर्माना", "पेनल्टी", "दंड", "દંડ", "પેનલ્ટી", "ਜੁਰਮਾਨਾ", "ਪੈਨਲਟੀ"],
        "answer": {
            "hinglish": "Haan. Outlet lambe samay tak band rahe toh bank penalty lagata hai. Isliye roz chalana zaroori hai.",
            "en": "Yes. If the outlet stays closed for long, the bank charges a penalty. So it must open every day.",
            "hi": "हाँ। आउटलेट लंबे समय तक बंद रहे तो बैंक पेनल्टी लगाता है। इसलिए रोज़ चलाना ज़रूरी है।",
            "gu": "હા. આઉટલેટ લાંબા સમય સુધી બંધ રહે તો બેંક દંડ લગાવે છે. તેથી રોજ ચલાવવું જરૂરી છે.",
            "pa": "ਹਾਂ। ਆਊਟਲੈੱਟ ਲੰਮੇ ਸਮੇਂ ਤੱਕ ਬੰਦ ਰਹੇ ਤਾਂ ਬੈਂਕ ਜੁਰਮਾਨਾ ਲਗਾਉਂਦਾ ਹੈ। ਇਸ ਲਈ ਰੋਜ਼ ਚਲਾਉਣਾ ਜ਼ਰੂਰੀ ਹੈ।",
        },
    },
    {
        "id": "customer_charges", "question": "Customer se charge kaun leta hai?",
        "keys": ["customer se charge", "graahak se", "grahak se", "customer charge", "service charge", "charges", "ग्राहक से", "चार्ज", "ગ્રાહક પાસેથી", "ચાર્જ", "ਗਾਹਕ ਤੋਂ", "ਚਾਰਜ"],
        "answer": {
            "hinglish": "Counter par har charge bank tay karta hai. Eko customer se koi charge nahi leta.",
            "en": "The bank sets every charge at the counter. Eko does not charge customers anything.",
            "hi": "काउंटर पर हर चार्ज बैंक तय करता है। Eko ग्राहक से कोई चार्ज नहीं लेता।",
            "gu": "કાઉન્ટર પર દરેક ચાર્જ બેંક નક્કી કરે છે. Eko ગ્રાહક પાસેથી કોઈ ચાર્જ લેતું નથી.",
            "pa": "ਕਾਊਂਟਰ 'ਤੇ ਹਰ ਚਾਰਜ ਬੈਂਕ ਤੈਅ ਕਰਦਾ ਹੈ। Eko ਗਾਹਕ ਤੋਂ ਕੋਈ ਚਾਰਜ ਨਹੀਂ ਲੈਂਦਾ।",
        },
    },
]

# From Eko's own site, kiosk.eko.in (read 2026-10-16): who can apply, the
# documents, the steps, the services and how commission is paid. Kept apart
# from the Creator Pack's confirmed answers, which stay as they are; where the
# site says "mini branch" or names a monthly figure, the team's word rules win
# and those are left out.
SITE_FAQ: List[dict] = [
    {
        "id": "eligibility", "question": "Kaun apply kar sakta hai? Eligibility kya hai?", "source": "kiosk.eko.in",
        "keys": ["eligibility", "eligible", "yogyata", "yogya", "kaun apply", "kon apply", "who can apply", "criteria",
                 "shart", "sharten", "political", "party member", "bank employee", "bank mein kaam", "योग्यता", "पात्रता",
                 "कौन आवेदन", "શરતો", "પાત્રતા", "યોગ્યતા", "ਯੋਗਤਾ"],
        "answer": {
            "hinglish": "Kam se kam 12th pass; CIBIL score 0 (koi loan history nahi) ya 700+; computer ki basic jaankari; smartphone, tablet ya laptop; market ya residential ilaake mein apni ya kiraye ki jagah. Aap kisi bank ya financial institution mein naukri na karte hon aur kisi political party ke member na hon. Gaon aur kasbon ke log khas taur par.",
            "en": "At least 12th pass; a CIBIL score of 0 (no credit history) or 700+; basic computer knowledge; a smartphone, tablet or laptop; your own or rented space in a market or residential area. You must not be employed with any bank or financial institution, nor be a member of a political party. Rural and semi-urban areas are preferred.",
            "hi": "कम से कम 12वीं पास; CIBIL स्कोर 0 (कोई लोन हिस्ट्री नहीं) या 700+; कंप्यूटर की बुनियादी जानकारी; स्मार्टफोन, टैबलेट या लैपटॉप; मार्केट या रिहायशी इलाके में अपनी या किराए की जगह। आप किसी बैंक या वित्तीय संस्था में नौकरी न करते हों और किसी राजनीतिक दल के सदस्य न हों। ग्रामीण और कस्बाई इलाकों को प्राथमिकता।",
            "gu": "ઓછામાં ઓછું 12મું પાસ; CIBIL સ્કોર 0 (કોઈ લોન હિસ્ટ્રી નહીં) અથવા 700+; કમ્પ્યુટરની મૂળભૂત જાણકારી; સ્માર્ટફોન, ટેબ્લેટ અથવા લેપટોપ; બજાર કે રહેણાંક વિસ્તારમાં પોતાની કે ભાડાની જગ્યા. તમે કોઈ બેંક કે નાણાકીય સંસ્થામાં નોકરી ન કરતા હો અને કોઈ રાજકીય પક્ષના સભ્ય ન હો. ગ્રામ્ય અને અર્ધ-શહેરી વિસ્તારોને પ્રાથમિકતા.",
            "pa": "ਘੱਟੋ-ਘੱਟ 12ਵੀਂ ਪਾਸ; CIBIL ਸਕੋਰ 0 (ਕੋਈ ਲੋਨ ਹਿਸਟਰੀ ਨਹੀਂ) ਜਾਂ 700+; ਕੰਪਿਊਟਰ ਦੀ ਮੁੱਢਲੀ ਜਾਣਕਾਰੀ; ਸਮਾਰਟਫੋਨ, ਟੈਬਲੇਟ ਜਾਂ ਲੈਪਟਾਪ; ਬਾਜ਼ਾਰ ਜਾਂ ਰਿਹਾਇਸ਼ੀ ਇਲਾਕੇ ਵਿੱਚ ਆਪਣੀ ਜਾਂ ਕਿਰਾਏ ਦੀ ਜਗ੍ਹਾ। ਤੁਸੀਂ ਕਿਸੇ ਬੈਂਕ ਜਾਂ ਵਿੱਤੀ ਸੰਸਥਾ ਵਿੱਚ ਨੌਕਰੀ ਨਾ ਕਰਦੇ ਹੋਵੋ ਅਤੇ ਕਿਸੇ ਰਾਜਨੀਤਿਕ ਪਾਰਟੀ ਦੇ ਮੈਂਬਰ ਨਾ ਹੋਵੋ। ਪਿੰਡਾਂ ਅਤੇ ਕਸਬਿਆਂ ਨੂੰ ਤਰਜੀਹ।",
        },
    },
    {
        "id": "cibil", "question": "CIBIL score kitna chahiye?", "source": "kiosk.eko.in",
        "keys": ["cibil", "sibil", "civil score", "credit score", "cibil score", "loan history", "सिबिल", "क्रेडिट स्कोर", "સિબિલ", "ਸਿਬਿਲ"],
        "answer": {
            "hinglish": "CIBIL score 0 hona chahiye (yaani koi loan history nahi) ya 700 se upar. Full CIBIL report documents ke saath lagti hai.",
            "en": "Your CIBIL score should be 0 (no credit history) or above 700. The full CIBIL report goes with your documents.",
            "hi": "CIBIL स्कोर 0 होना चाहिए (यानी कोई लोन हिस्ट्री नहीं) या 700 से ऊपर। पूरी CIBIL रिपोर्ट डॉक्यूमेंट्स के साथ लगती है।",
            "gu": "CIBIL સ્કોર 0 (એટલે કે કોઈ લોન હિસ્ટ્રી નહીં) અથવા 700થી વધુ હોવો જોઈએ. સંપૂર્ણ CIBIL રિપોર્ટ દસ્તાવેજો સાથે જોડાય છે.",
            "pa": "CIBIL ਸਕੋਰ 0 ਹੋਣਾ ਚਾਹੀਦਾ ਹੈ (ਯਾਨੀ ਕੋਈ ਲੋਨ ਹਿਸਟਰੀ ਨਹੀਂ) ਜਾਂ 700 ਤੋਂ ਉੱਪਰ। ਪੂਰੀ CIBIL ਰਿਪੋਰਟ ਦਸਤਾਵੇਜ਼ਾਂ ਨਾਲ ਲੱਗਦੀ ਹੈ।",
        },
    },
    {
        "id": "documents", "question": "Kaun se documents chahiye?", "source": "kiosk.eko.in",
        "keys": ["documents", "document", "dastavez", "dastavej", "kagaz", "kaagaz", "papers", "kya kya chahiye", "pvr",
                 "kya kya documents", "kaun se documents", "documents chahiye", "konse documents",
                 "police verification", "दस्तावेज", "दस्तावेज़", "कागज", "डॉक्यूमेंट", "દસ્તાવેજ", "કાગળ", "ਦਸਤਾਵੇਜ਼", "ਕਾਗਜ਼"],
        "answer": {
            "hinglish": "PAN card, Aadhaar card, passport size photo, Police Verification Certificate (ya uski application ki receipt), SBI account ki passbook ya statement (commission isi mein aata hai), 12th ka certificate, aur full CIBIL report. Address proof ke liye bijli ka bill ya registry bhi chalegi.",
            "en": "PAN card, Aadhaar card, a passport-size photo, a Police Verification Certificate (or its application receipt), your SBI account passbook or statement (commission is paid into it), your 12th certificate and the full CIBIL report. An electricity bill or registry papers work as address proof.",
            "hi": "PAN कार्ड, आधार कार्ड, पासपोर्ट साइज़ फोटो, पुलिस वेरिफिकेशन सर्टिफिकेट (या उसकी एप्लीकेशन की रसीद), SBI खाते की पासबुक या स्टेटमेंट (कमीशन इसी में आता है), 12वीं का सर्टिफिकेट, और पूरी CIBIL रिपोर्ट। पते के प्रमाण के लिए बिजली का बिल या रजिस्ट्री भी चलेगी।",
            "gu": "PAN કાર્ડ, આધાર કાર્ડ, પાસપોર્ટ સાઇઝ ફોટો, પોલીસ વેરિફિકેશન સર્ટિફિકેટ (અથવા તેની અરજીની રસીદ), SBI ખાતાની પાસબુક કે સ્ટેટમેન્ટ (કમિશન આમાં જ આવે છે), 12માનું સર્ટિફિકેટ, અને સંપૂર્ણ CIBIL રિપોર્ટ. સરનામાના પુરાવા માટે વીજળી બિલ કે દસ્તાવેજ પણ ચાલશે.",
            "pa": "PAN ਕਾਰਡ, ਆਧਾਰ ਕਾਰਡ, ਪਾਸਪੋਰਟ ਸਾਈਜ਼ ਫੋਟੋ, ਪੁਲਿਸ ਵੈਰੀਫਿਕੇਸ਼ਨ ਸਰਟੀਫਿਕੇਟ (ਜਾਂ ਉਸ ਦੀ ਅਰਜ਼ੀ ਦੀ ਰਸੀਦ), SBI ਖਾਤੇ ਦੀ ਪਾਸਬੁੱਕ ਜਾਂ ਸਟੇਟਮੈਂਟ (ਕਮਿਸ਼ਨ ਇਸੇ ਵਿੱਚ ਆਉਂਦਾ ਹੈ), 12ਵੀਂ ਦਾ ਸਰਟੀਫਿਕੇਟ, ਅਤੇ ਪੂਰੀ CIBIL ਰਿਪੋਰਟ। ਪਤੇ ਦੇ ਸਬੂਤ ਲਈ ਬਿਜਲੀ ਦਾ ਬਿੱਲ ਜਾਂ ਰਜਿਸਟਰੀ ਵੀ ਚੱਲੇਗੀ।",
        },
    },
    {
        "id": "commission_paid", "question": "Commission kab aur kahan milta hai?", "source": "kiosk.eko.in",
        "keys": ["commission kab", "kab milega commission", "payment kab", "paisa kab", "settlement",
                 "kis account", "kahan aayega", "कमीशन कब", "पैसा कब", "भुगतान कब", "કમિશન ક્યારે", "પૈસા ક્યારે", "ਕਮਿਸ਼ਨ ਕਦੋਂ", "ਪੈਸੇ ਕਦੋਂ"],
        "answer": {
            "hinglish": "Commission har mahine ki 10 tareekh se pehle seedha aapke registered SBI savings account mein aata hai, wahi account jo onboarding mein diya tha.",
            "en": "Commission is paid straight into your registered SBI savings account before the 10th of every month, the same account you gave at onboarding.",
            "hi": "कमीशन हर महीने की 10 तारीख से पहले सीधे आपके रजिस्टर्ड SBI सेविंग्स खाते में आता है, वही खाता जो ऑनबोर्डिंग में दिया था।",
            "gu": "કમિશન દર મહિનાની 10 તારીખ પહેલાં સીધું તમારા રજિસ્ટર્ડ SBI સેવિંગ્સ ખાતામાં આવે છે, એ જ ખાતું જે ઓનબોર્ડિંગમાં આપ્યું હતું.",
            "pa": "ਕਮਿਸ਼ਨ ਹਰ ਮਹੀਨੇ ਦੀ 10 ਤਰੀਕ ਤੋਂ ਪਹਿਲਾਂ ਸਿੱਧਾ ਤੁਹਾਡੇ ਰਜਿਸਟਰਡ SBI ਸੇਵਿੰਗਜ਼ ਖਾਤੇ ਵਿੱਚ ਆਉਂਦਾ ਹੈ, ਉਹੀ ਖਾਤਾ ਜੋ ਆਨਬੋਰਡਿੰਗ ਵਿੱਚ ਦਿੱਤਾ ਸੀ।",
        },
    },
    {
        "id": "process", "question": "Process kya hai? Kaise shuru hoga?", "source": "kiosk.eko.in",
        "keys": ["process", "prakriya", "steps", "kaise shuru", "kaise start", "how to become", "how to start",
                 "approval", "प्रक्रिया", "कैसे शुरू", "પ્રક્રિયા", "કેવી રીતે શરૂ", "ਪ੍ਰਕਿਰਿਆ", "ਕਿਵੇਂ ਸ਼ੁਰੂ"],
        "answer": {
            "hinglish": "6 kadam: 1) documents jama karein, 2) SBI approve karta hai, 3) devices aur kiosk ki setting, 4) Hindi mein digital training, 5) IIBF certification, 6) kaam aur kamaai shuru. Har kadam par Eko ki team saath rehti hai.",
            "en": "Six steps: 1) submit your documents, 2) SBI approves them, 3) the devices and the kiosk are set up, 4) digital training in Hindi, 5) IIBF certification, 6) you start serving customers and earning. Eko's team is with you at every step.",
            "hi": "6 कदम: 1) डॉक्यूमेंट्स जमा करें, 2) SBI अप्रूव करता है, 3) डिवाइस और कियोस्क की सेटिंग, 4) हिंदी में डिजिटल ट्रेनिंग, 5) IIBF सर्टिफिकेशन, 6) काम और कमाई शुरू। हर कदम पर Eko की टीम साथ रहती है।",
            "gu": "6 પગલાં: 1) દસ્તાવેજો જમા કરો, 2) SBI મંજૂર કરે છે, 3) ડિવાઇસ અને કિઓસ્કની ગોઠવણી, 4) હિન્દીમાં ડિજિટલ તાલીમ, 5) IIBF સર્ટિફિકેશન, 6) કામ અને કમાણી શરૂ. દરેક પગલે Ekoની ટીમ સાથે રહે છે.",
            "pa": "6 ਕਦਮ: 1) ਦਸਤਾਵੇਜ਼ ਜਮ੍ਹਾਂ ਕਰੋ, 2) SBI ਮਨਜ਼ੂਰ ਕਰਦਾ ਹੈ, 3) ਡਿਵਾਈਸ ਅਤੇ ਕਿਓਸਕ ਦੀ ਸੈਟਿੰਗ, 4) ਹਿੰਦੀ ਵਿੱਚ ਡਿਜੀਟਲ ਟ੍ਰੇਨਿੰਗ, 5) IIBF ਸਰਟੀਫਿਕੇਸ਼ਨ, 6) ਕੰਮ ਅਤੇ ਕਮਾਈ ਸ਼ੁਰੂ। ਹਰ ਕਦਮ 'ਤੇ Eko ਦੀ ਟੀਮ ਨਾਲ ਰਹਿੰਦੀ ਹੈ।",
        },
    },
    {
        "id": "services", "question": "Kaun si sevayein de sakte hain?", "source": "kiosk.eko.in",
        # Not "services" or "seva": the Creator Pack's earning_lines answer has those.
        "keys": ["44 services", "kitni services", "kitni sevayein", "kya kya kar sakte", "kya kaam hoga", "account khol",
                 "aeps kar sakte", "money transfer", "pmjdy", "kaun kaun si sevayein",
                 "सेवाएं", "કઈ સેવાઓ", "ਕਿਹੜੀਆਂ ਸੇਵਾਵਾਂ"],
        "answer": {
            "hinglish": "SBI ki 44+ sevayein: paise jama aur nikaalna, balance aur mini statement, passbook update, IMPS/NEFT money transfer, khata kholna (PMJDY), Aadhaar seeding, debit card aur cheque book ki request, RD/TD, PPF/SSA jama, PMSBY, PMJJBY aur Atal Pension Yojana, loan aur insurance ke leads, bill payment, recharge aur FASTag.",
            "en": "44+ SBI services: cash deposit and withdrawal, balance and mini statement, passbook update, IMPS/NEFT money transfer, account opening (PMJDY), Aadhaar seeding, debit card and cheque book requests, RD/TD, PPF/SSA deposits, PMSBY, PMJJBY and Atal Pension Yojana, loan and insurance leads, bill payments, recharges and FASTag.",
            "hi": "SBI की 44+ सेवाएँ: पैसे जमा और निकालना, बैलेंस और मिनी स्टेटमेंट, पासबुक अपडेट, IMPS/NEFT मनी ट्रांसफर, खाता खोलना (PMJDY), आधार सीडिंग, डेबिट कार्ड और चेक बुक की रिक्वेस्ट, RD/TD, PPF/SSA जमा, PMSBY, PMJJBY और अटल पेंशन योजना, लोन और इंश्योरेंस के लीड, बिल पेमेंट, रिचार्ज और FASTag।",
            "gu": "SBIની 44+ સેવાઓ: પૈસા જમા અને ઉપાડ, બેલેન્સ અને મિની સ્ટેટમેન્ટ, પાસબુક અપડેટ, IMPS/NEFT મની ટ્રાન્સફર, ખાતું ખોલવું (PMJDY), આધાર સીડિંગ, ડેબિટ કાર્ડ અને ચેકબુકની વિનંતી, RD/TD, PPF/SSA જમા, PMSBY, PMJJBY અને અટલ પેન્શન યોજના, લોન અને વીમાના લીડ, બિલ પેમેન્ટ, રિચાર્જ અને FASTag.",
            "pa": "SBI ਦੀਆਂ 44+ ਸੇਵਾਵਾਂ: ਪੈਸੇ ਜਮ੍ਹਾਂ ਕਰਨਾ ਅਤੇ ਕਢਵਾਉਣਾ, ਬੈਲੇਂਸ ਅਤੇ ਮਿੰਨੀ ਸਟੇਟਮੈਂਟ, ਪਾਸਬੁੱਕ ਅਪਡੇਟ, IMPS/NEFT ਮਨੀ ਟ੍ਰਾਂਸਫਰ, ਖਾਤਾ ਖੋਲ੍ਹਣਾ (PMJDY), ਆਧਾਰ ਸੀਡਿੰਗ, ਡੈਬਿਟ ਕਾਰਡ ਅਤੇ ਚੈੱਕ ਬੁੱਕ ਦੀ ਬੇਨਤੀ, RD/TD, PPF/SSA ਜਮ੍ਹਾਂ, PMSBY, PMJJBY ਅਤੇ ਅਟਲ ਪੈਨਸ਼ਨ ਯੋਜਨਾ, ਲੋਨ ਅਤੇ ਬੀਮੇ ਦੇ ਲੀਡ, ਬਿੱਲ ਪੇਮੈਂਟ, ਰੀਚਾਰਜ ਅਤੇ FASTag।",
        },
    },
    {
        "id": "reach", "question": "Eko kitni jagah kaam karta hai?", "source": "kiosk.eko.in",
        "keys": ["kitne csp", "kitni jagah", "kahan kahan", "kaha kaha", "districts", "how many csp", "कितने सीएसपी",
                 "कहाँ कहाँ", "ક્યાં ક્યાં", "ਕਿੱਥੇ ਕਿੱਥੇ"],
        "answer": {
            "hinglish": "Eko ke 1,100 se zyada CSP 160+ districts mein kaam kar rahe hain, Punjab, Haryana, UP, Bihar, Rajasthan, Maharashtra, Jharkhand, Delhi NCR, J&K aur Himachal mein.",
            "en": "Over 1,100 Eko CSPs work in 160+ districts, across Punjab, Haryana, UP, Bihar, Rajasthan, Maharashtra, Jharkhand, Delhi NCR, J&K and Himachal.",
            "hi": "Eko के 1,100 से ज़्यादा CSP 160+ ज़िलों में काम कर रहे हैं, पंजाब, हरियाणा, यूपी, बिहार, राजस्थान, महाराष्ट्र, झारखंड, दिल्ली NCR, J&K और हिमाचल में।",
            "gu": "Ekoના 1,100થી વધુ CSP 160+ જિલ્લાઓમાં કામ કરે છે, પંજાબ, હરિયાણા, યુપી, બિહાર, રાજસ્થાન, મહારાષ્ટ્ર, ઝારખંડ, દિલ્હી NCR, J&K અને હિમાચલમાં.",
            "pa": "Eko ਦੇ 1,100 ਤੋਂ ਵੱਧ CSP 160+ ਜ਼ਿਲ੍ਹਿਆਂ ਵਿੱਚ ਕੰਮ ਕਰ ਰਹੇ ਹਨ, ਪੰਜਾਬ, ਹਰਿਆਣਾ, ਯੂਪੀ, ਬਿਹਾਰ, ਰਾਜਸਥਾਨ, ਮਹਾਰਾਸ਼ਟਰ, ਝਾਰਖੰਡ, ਦਿੱਲੀ NCR, J&K ਅਤੇ ਹਿਮਾਚਲ ਵਿੱਚ।",
        },
    },
]
# The rest of kiosk.eko.in (2026-10-18: the team asked for all of it). The
# earnings figures are the site's own, said with its own warning that most
# CSPs earn far less; the outlet is still never called a mini bank or branch.
SITE_FAQ += [
    {
        "id": "what_csp", "question": "CSP kya hota hai?", "source": "kiosk.eko.in",
        "keys": ["csp kya hai", "csp kya hota", "customer service point", "kiosk kya hai", "kiosk kya hota",
                 "banking outlet kya", "what is csp", "what is a csp", "kiosk operator kya", "सीएसपी क्या", "कियोस्क क्या",
                 "સીએસપી શું", "ਸੀਐਸਪੀ ਕੀ"],
        "answer": {
            "hinglish": "CSP (Customer Service Point) ek authorised banking outlet hai jo Kiosk Operator chalata hai, Eko ke SBI-backed platform par. Yahan se aap apne ilaake ke logon ko khata kholna, paise jama aur nikaalna, money transfer aur SBI ki 44+ banking sevayein dete hain.",
            "en": "A CSP (Customer Service Point) is an authorised banking outlet run by a Kiosk Operator on Eko's SBI-backed platform. From it you give people in your area account opening, cash deposit and withdrawal, money transfer and 44+ other SBI banking services.",
            "hi": "CSP (कस्टमर सर्विस पॉइंट) एक अधिकृत बैंकिंग आउटलेट है जिसे Kiosk Operator, Eko के SBI-समर्थित प्लेटफ़ॉर्म पर चलाता है। यहाँ से आप अपने इलाके के लोगों को खाता खोलना, पैसे जमा और निकालना, मनी ट्रांसफर और SBI की 44+ बैंकिंग सेवाएँ देते हैं।",
            "gu": "CSP (કસ્ટમર સર્વિસ પોઇન્ટ) એક અધિકૃત બેંકિંગ આઉટલેટ છે જે Kiosk Operator, Ekoના SBI-સમર્થિત પ્લેટફોર્મ પર ચલાવે છે. અહીંથી તમે તમારા વિસ્તારના લોકોને ખાતું ખોલવું, પૈસા જમા અને ઉપાડ, મની ટ્રાન્સફર અને SBIની 44+ બેંકિંગ સેવાઓ આપો છો.",
            "pa": "CSP (ਕਸਟਮਰ ਸਰਵਿਸ ਪੁਆਇੰਟ) ਇੱਕ ਅਧਿਕਾਰਤ ਬੈਂਕਿੰਗ ਆਊਟਲੈੱਟ ਹੈ ਜਿਸਨੂੰ Kiosk Operator, Eko ਦੇ SBI-ਸਮਰਥਿਤ ਪਲੇਟਫਾਰਮ 'ਤੇ ਚਲਾਉਂਦਾ ਹੈ। ਇੱਥੋਂ ਤੁਸੀਂ ਆਪਣੇ ਇਲਾਕੇ ਦੇ ਲੋਕਾਂ ਨੂੰ ਖਾਤਾ ਖੋਲ੍ਹਣਾ, ਪੈਸੇ ਜਮ੍ਹਾਂ ਕਰਨਾ ਅਤੇ ਕਢਵਾਉਣਾ, ਮਨੀ ਟ੍ਰਾਂਸਫਰ ਅਤੇ SBI ਦੀਆਂ 44+ ਬੈਂਕਿੰਗ ਸੇਵਾਵਾਂ ਦਿੰਦੇ ਹੋ।",
        },
    },
    {
        "id": "setup_cost", "question": "Setup ka kharcha hai?", "source": "kiosk.eko.in",
        "keys": ["setup cost", "setup ka kharcha", "setup charge", "one time", "ek baar ka", "installation charge",
                 "device ka kharcha", "machine ka paisa", "machine ke paise", "branding ka", "सेटअप का खर्च", "एक बार का",
                 "સેટઅપ ખર્ચ", "ਸੈੱਟਅਪ ਖਰਚਾ"],
        "answer": {
            "hinglish": "Haan. Ek baar ka investment lagta hai jisme Micro-ATM, biometric scanner aur kiosk ki branding aati hai (kul milakar ₹5 lakh tak, location aur setup ke hisaab se). Kuch bhi tay karne se pehle aapka onboarding coordinator poora hisaab batata hai.",
            "en": "Yes. There is a one-time investment that covers the Micro-ATM, the biometric scanner and the kiosk branding (up to ₹5 lakh in all, depending on location and setup). Your onboarding coordinator shares the full breakdown before you commit to anything.",
            "hi": "हाँ। एक बार का निवेश लगता है जिसमें माइक्रो-ATM, बायोमेट्रिक स्कैनर और कियोस्क की ब्रांडिंग आती है (कुल मिलाकर ₹5 लाख तक, लोकेशन और सेटअप के हिसाब से)। कुछ भी तय करने से पहले आपका ऑनबोर्डिंग कोऑर्डिनेटर पूरा हिसाब बताता है।",
            "gu": "હા. એક વખતનું રોકાણ લાગે છે જેમાં માઇક્રો-ATM, બાયોમેટ્રિક સ્કેનર અને કિઓસ્કની બ્રાન્ડિંગ આવે છે (કુલ ₹5 લાખ સુધી, સ્થળ અને સેટઅપ પ્રમાણે). કંઈ પણ નક્કી કરતાં પહેલાં તમારા ઓનબોર્ડિંગ કોઓર્ડિનેટર આખો હિસાબ જણાવે છે.",
            "pa": "ਹਾਂ। ਇੱਕ ਵਾਰ ਦਾ ਨਿਵੇਸ਼ ਲੱਗਦਾ ਹੈ ਜਿਸ ਵਿੱਚ ਮਾਈਕ੍ਰੋ-ATM, ਬਾਇਓਮੈਟ੍ਰਿਕ ਸਕੈਨਰ ਅਤੇ ਕਿਓਸਕ ਦੀ ਬ੍ਰਾਂਡਿੰਗ ਆਉਂਦੀ ਹੈ (ਕੁੱਲ ₹5 ਲੱਖ ਤੱਕ, ਲੋਕੇਸ਼ਨ ਅਤੇ ਸੈੱਟਅਪ ਮੁਤਾਬਕ)। ਕੁਝ ਵੀ ਤੈਅ ਕਰਨ ਤੋਂ ਪਹਿਲਾਂ ਤੁਹਾਡਾ ਆਨਬੋਰਡਿੰਗ ਕੋਆਰਡੀਨੇਟਰ ਪੂਰਾ ਹਿਸਾਬ ਦੱਸਦਾ ਹੈ।",
        },
    },
    {
        "id": "who_fits", "question": "Kaun log ye achha chala paate hain?", "source": "kiosk.eko.in",
        "keys": ["dukaan wale", "dukan wala", "shop owner", "shopkeeper", "ghar se chala", "home based", "pehli baar",
                 "first time", "naya business", "student", "youth", "berozgar", "housewife", "grihini", "shg", "self help group",
                 "finance background", "banking experience", "experience chahiye", "अनुभव", "दुकानदार", "गृहिणी", "અનુભવ",
                 "દુકાનદાર", "ਤਜਰਬਾ", "ਦੁਕਾਨਦਾਰ"],
        "answer": {
            "hinglish": "Finance ka background zaroori nahi, apne ilaake ka bharosa zaroori hai. Pehli baar business karne wale aur ghar se chalane wale, market ya mohalle mein dukaan wale, naukri dhundh rahe padhe-likhe yuva, aur NGO ya Self-Help Group se aaye log, sab achha karte hain. 12th pass aur CIBIL ki shart sab par lagu hai.",
            "en": "You don't need a finance background, you need your community's trust. First-time and home-based operators, shop owners in a market or neighbourhood, educated youth looking for steady income, and people nominated by an NGO or Self-Help Group all do well. The 12th-pass and CIBIL requirements apply to everyone.",
            "hi": "फाइनेंस का बैकग्राउंड ज़रूरी नहीं, अपने इलाके का भरोसा ज़रूरी है। पहली बार बिज़नेस करने वाले और घर से चलाने वाले, बाज़ार या मोहल्ले में दुकान वाले, नौकरी ढूँढ रहे पढ़े-लिखे युवा, और NGO या स्वयं सहायता समूह से आए लोग, सब अच्छा करते हैं। 12वीं पास और CIBIL की शर्त सब पर लागू है।",
            "gu": "ફાઇનાન્સનું બેકગ્રાઉન્ડ જરૂરી નથી, તમારા વિસ્તારનો ભરોસો જરૂરી છે. પહેલી વાર બિઝનેસ કરનાર અને ઘરેથી ચલાવનાર, બજાર કે મહોલ્લામાં દુકાનવાળા, નોકરી શોધતા ભણેલા યુવાનો, અને NGO કે સ્વ-સહાય જૂથથી આવેલા લોકો, બધા સારું કરે છે. 12મું પાસ અને CIBILની શરત બધાને લાગુ પડે છે.",
            "pa": "ਫਾਇਨਾਂਸ ਦਾ ਬੈਕਗ੍ਰਾਊਂਡ ਜ਼ਰੂਰੀ ਨਹੀਂ, ਆਪਣੇ ਇਲਾਕੇ ਦਾ ਭਰੋਸਾ ਜ਼ਰੂਰੀ ਹੈ। ਪਹਿਲੀ ਵਾਰ ਕਾਰੋਬਾਰ ਕਰਨ ਵਾਲੇ ਅਤੇ ਘਰੋਂ ਚਲਾਉਣ ਵਾਲੇ, ਬਾਜ਼ਾਰ ਜਾਂ ਮੁਹੱਲੇ ਵਿੱਚ ਦੁਕਾਨ ਵਾਲੇ, ਨੌਕਰੀ ਲੱਭ ਰਹੇ ਪੜ੍ਹੇ-ਲਿਖੇ ਨੌਜਵਾਨ, ਅਤੇ NGO ਜਾਂ ਸਵੈ-ਸਹਾਇਤਾ ਸਮੂਹ ਤੋਂ ਆਏ ਲੋਕ, ਸਾਰੇ ਵਧੀਆ ਕਰਦੇ ਹਨ। 12ਵੀਂ ਪਾਸ ਅਤੇ CIBIL ਦੀ ਸ਼ਰਤ ਸਾਰਿਆਂ 'ਤੇ ਲਾਗੂ ਹੈ।",
        },
    },
    {
        "id": "schemes", "question": "Kaun si sarkari yojanayein?", "source": "kiosk.eko.in",
        "keys": ["yojana", "yojna", "scheme", "schemes", "sarkari yojana", "pmsby", "pmjjby", "atal pension", "apy",
                 "bima yojana", "pension", "insurance scheme", "योजना", "पेंशन", "બીમા યોજના", "યોજના", "ਯੋਜਨਾ"],
        "answer": {
            "hinglish": "CSP par sarkari yojanaon mein enrolment hota hai: PMSBY (accident cover ₹20 saal), PMJJBY (life cover ₹436 saal) aur Atal Pension Yojana. Har enrolment par commission/incentive milta hai.",
            "en": "A CSP enrols people in government schemes: PMSBY (accident cover, ₹20 a year), PMJJBY (life cover, ₹436 a year) and the Atal Pension Yojana. Each enrolment earns a commission or incentive.",
            "hi": "CSP पर सरकारी योजनाओं में नामांकन होता है: PMSBY (दुर्घटना कवर ₹20 सालाना), PMJJBY (जीवन कवर ₹436 सालाना) और अटल पेंशन योजना। हर नामांकन पर कमीशन/इंसेंटिव मिलता है।",
            "gu": "CSP પર સરકારી યોજનાઓમાં નોંધણી થાય છે: PMSBY (અકસ્માત કવર ₹20 વાર્ષિક), PMJJBY (જીવન કવર ₹436 વાર્ષિક) અને અટલ પેન્શન યોજના. દરેક નોંધણી પર કમિશન/ઇન્સેન્ટિવ મળે છે.",
            "pa": "CSP 'ਤੇ ਸਰਕਾਰੀ ਯੋਜਨਾਵਾਂ ਵਿੱਚ ਨਾਮਾਂਕਣ ਹੁੰਦਾ ਹੈ: PMSBY (ਦੁਰਘਟਨਾ ਕਵਰ ₹20 ਸਾਲਾਨਾ), PMJJBY (ਜੀਵਨ ਕਵਰ ₹436 ਸਾਲਾਨਾ) ਅਤੇ ਅਟਲ ਪੈਨਸ਼ਨ ਯੋਜਨਾ। ਹਰ ਨਾਮਾਂਕਣ 'ਤੇ ਕਮਿਸ਼ਨ/ਇੰਸੈਂਟਿਵ ਮਿਲਦਾ ਹੈ।",
        },
    },
    {
        "id": "security", "question": "Data aur transaction safe hai?", "source": "kiosk.eko.in",
        "keys": ["online fraud", "fraud ka darr", "darr hai", "security", "secure", "safe hai", "surakshit", "suraksha", "data safe", "hack", "encryption", "gps",
                 "fraud se bachav", "सुरक्षित", "सुरक्षा", "સુરક્ષિત", "ਸੁਰੱਖਿਅਤ"],
        "answer": {
            "hinglish": "Haan. Saara data end-to-end encryption se surakshit hai, RBI ke 2024–25 Cyber Resilience niyamon ke hisaab se. Har AePS transaction GPS-tagged hota hai aur kuch bhi asaamanya ho to apne aap flag hota hai. Bank ke coordinator audit aur surprise visit bhi karte hain.",
            "en": "Yes. All data is protected with end-to-end encryption, in line with RBI's 2024–25 Master Directions on Cyber Resilience. Every AePS transaction is GPS-tagged and unusual activity is flagged automatically. Bank coordinators also run audits and surprise visits.",
            "hi": "हाँ। सारा डेटा एंड-टू-एंड एन्क्रिप्शन से सुरक्षित है, RBI के 2024–25 साइबर रेज़िलिएंस नियमों के अनुसार। हर AePS ट्रांज़ैक्शन GPS-टैग होता है और कुछ भी असामान्य हो तो अपने आप फ़्लैग होता है। बैंक के कोऑर्डिनेटर ऑडिट और सरप्राइज़ विज़िट भी करते हैं।",
            "gu": "હા. બધો ડેટા એન્ડ-ટુ-એન્ડ એન્ક્રિપ્શનથી સુરક્ષિત છે, RBIના 2024–25 સાયબર રેઝિલિયન્સ નિયમો મુજબ. દરેક AePS ટ્રાન્ઝેક્શન GPS-ટેગ થાય છે અને કંઈ પણ અસામાન્ય હોય તો આપમેળે ફ્લેગ થાય છે. બેંકના કોઓર્ડિનેટર ઓડિટ અને સરપ્રાઇઝ વિઝિટ પણ કરે છે.",
            "pa": "ਹਾਂ। ਸਾਰਾ ਡੇਟਾ ਐਂਡ-ਟੂ-ਐਂਡ ਐਨਕ੍ਰਿਪਸ਼ਨ ਨਾਲ ਸੁਰੱਖਿਅਤ ਹੈ, RBI ਦੇ 2024–25 ਸਾਈਬਰ ਰੈਜ਼ੀਲੀਅੰਸ ਨਿਯਮਾਂ ਮੁਤਾਬਕ। ਹਰ AePS ਟ੍ਰਾਂਜ਼ੈਕਸ਼ਨ GPS-ਟੈਗ ਹੁੰਦਾ ਹੈ ਅਤੇ ਕੁਝ ਵੀ ਅਸਧਾਰਨ ਹੋਵੇ ਤਾਂ ਆਪਣੇ ਆਪ ਫਲੈਗ ਹੁੰਦਾ ਹੈ। ਬੈਂਕ ਦੇ ਕੋਆਰਡੀਨੇਟਰ ਆਡਿਟ ਅਤੇ ਸਰਪ੍ਰਾਈਜ਼ ਵਿਜ਼ਿਟ ਵੀ ਕਰਦੇ ਹਨ।",
        },
    },
    {
        "id": "audit", "question": "Kya check karne koi aayega?", "source": "kiosk.eko.in",
        "keys": ["audit", "inspection", "check karne", "jaanch", "janch", "verification visit", "surprise visit",
                 "koi aayega", "bank wale aayenge", "निरीक्षण", "जाँच", "ઓડિટ", "તપાસ", "ਜਾਂਚ"],
        "answer": {
            "hinglish": "Haan. Har Eko CSP bank branch jaise hi KYC/AML aur compliance niyamon par chalta hai. Concurrent audit hote hain aur bank ke coordinator bina bataye physical verification ke liye aa sakte hain. Branch manager live dashboard par transactions dekhte hain.",
            "en": "Yes. Every Eko CSP follows the same KYC/AML and compliance standards as a bank branch. There are concurrent audits, and bank coordinators can come unannounced for physical verification. Branch managers watch the transactions on a live dashboard.",
            "hi": "हाँ। हर Eko CSP बैंक ब्रांच जैसे ही KYC/AML और कंप्लायंस नियमों पर चलता है। कंकरेंट ऑडिट होते हैं और बैंक के कोऑर्डिनेटर बिना बताए फ़िज़िकल वेरिफ़िकेशन के लिए आ सकते हैं। ब्रांच मैनेजर लाइव डैशबोर्ड पर ट्रांज़ैक्शन देखते हैं।",
            "gu": "હા. દરેક Eko CSP બેંક બ્રાન્ચની જેમ જ KYC/AML અને કમ્પ્લાયન્સ નિયમો પર ચાલે છે. કન્કરન્ટ ઓડિટ થાય છે અને બેંકના કોઓર્ડિનેટર જાણ કર્યા વગર ફિઝિકલ વેરિફિકેશન માટે આવી શકે છે. બ્રાન્ચ મેનેજર લાઇવ ડેશબોર્ડ પર ટ્રાન્ઝેક્શન જુએ છે.",
            "pa": "ਹਾਂ। ਹਰ Eko CSP ਬੈਂਕ ਬ੍ਰਾਂਚ ਵਾਂਗ ਹੀ KYC/AML ਅਤੇ ਕੰਪਲਾਇੰਸ ਨਿਯਮਾਂ 'ਤੇ ਚੱਲਦਾ ਹੈ। ਕੰਕਰੰਟ ਆਡਿਟ ਹੁੰਦੇ ਹਨ ਅਤੇ ਬੈਂਕ ਦੇ ਕੋਆਰਡੀਨੇਟਰ ਬਿਨਾਂ ਦੱਸੇ ਫਿਜ਼ੀਕਲ ਵੈਰੀਫਿਕੇਸ਼ਨ ਲਈ ਆ ਸਕਦੇ ਹਨ। ਬ੍ਰਾਂਚ ਮੈਨੇਜਰ ਲਾਈਵ ਡੈਸ਼ਬੋਰਡ 'ਤੇ ਟ੍ਰਾਂਜ਼ੈਕਸ਼ਨ ਵੇਖਦੇ ਹਨ।",
        },
    },
    {
        "id": "ngo", "question": "NGO ya SHG kaise jud sakta hai?", "source": "kiosk.eko.in",
        "keys": ["ngo", "n g o", "ngo kaise jude", "ngo kaise", "ngo partner", "shg partner", "samuh", "sanstha", "federation", "csr", "donor", "funding", "partner banna",
                 "संस्था", "समूह", "સંસ્થા", "ਸੰਸਥਾ"],
        "answer": {
            "hinglish": "NGO aur SHG network Eko ke partner portal se jud sakte hain, bina kisi kharche ke. Aap apne samuh se logon ko Kiosk Operator banne ke liye nominate karte hain; Eko technology, bank ka saath, devices aur branding, training aur compliance deta hai. Donor ke liye equipment grant, working capital aur certification ka program bhi hai.",
            "en": "NGOs and SHG networks join through Eko's partner portal at no cost. You nominate people from your network to become Kiosk Operators; Eko provides the technology, the bank relationship, devices and branding, training and the compliance framework. Donors can fund equipment, working capital or certification.",
            "hi": "NGO और SHG नेटवर्क Eko के पार्टनर पोर्टल से जुड़ सकते हैं, बिना किसी खर्च के। आप अपने समूह से लोगों को Kiosk Operator बनने के लिए नॉमिनेट करते हैं; Eko टेक्नोलॉजी, बैंक का साथ, डिवाइस और ब्रांडिंग, ट्रेनिंग और कंप्लायंस देता है। डोनर के लिए उपकरण, वर्किंग कैपिटल और सर्टिफ़िकेशन का प्रोग्राम भी है।",
            "gu": "NGO અને SHG નેટવર્ક Ekoના પાર્ટનર પોર્ટલથી કોઈ ખર્ચ વગર જોડાઈ શકે છે. તમે તમારા જૂથમાંથી લોકોને Kiosk Operator બનવા માટે નોમિનેટ કરો છો; Eko ટેક્નોલોજી, બેંકનો સાથ, ડિવાઇસ અને બ્રાન્ડિંગ, તાલીમ અને કમ્પ્લાયન્સ આપે છે. દાતાઓ માટે સાધનો, વર્કિંગ કેપિટલ અને સર્ટિફિકેશનનો પ્રોગ્રામ પણ છે.",
            "pa": "NGO ਅਤੇ SHG ਨੈੱਟਵਰਕ Eko ਦੇ ਪਾਰਟਨਰ ਪੋਰਟਲ ਰਾਹੀਂ ਬਿਨਾਂ ਕਿਸੇ ਖਰਚੇ ਦੇ ਜੁੜ ਸਕਦੇ ਹਨ। ਤੁਸੀਂ ਆਪਣੇ ਸਮੂਹ ਤੋਂ ਲੋਕਾਂ ਨੂੰ Kiosk Operator ਬਣਨ ਲਈ ਨਾਮਜ਼ਦ ਕਰਦੇ ਹੋ; Eko ਤਕਨਾਲੋਜੀ, ਬੈਂਕ ਦਾ ਸਾਥ, ਡਿਵਾਈਸ ਅਤੇ ਬ੍ਰਾਂਡਿੰਗ, ਟ੍ਰੇਨਿੰਗ ਅਤੇ ਕੰਪਲਾਇੰਸ ਦਿੰਦਾ ਹੈ। ਦਾਨੀਆਂ ਲਈ ਉਪਕਰਣ, ਵਰਕਿੰਗ ਕੈਪੀਟਲ ਅਤੇ ਸਰਟੀਫਿਕੇਸ਼ਨ ਦਾ ਪ੍ਰੋਗਰਾਮ ਵੀ ਹੈ।",
        },
    },
    {
        "id": "apply_online", "question": "Website se apply kaise karein? Contact kab karenge?", "source": "kiosk.eko.in",
        "keys": ["website", "site se", "online apply", "apply kahan", "form kahan", "form bharna", "kiosk.eko.in",
                 "call kab", "contact kab", "kab call", "kab contact", "kab sampark", "वेबसाइट", "फॉर्म", "વેબસાઇટ", "ਵੈੱਬਸਾਈਟ"],
        "answer": {
            "hinglish": "Aap yahin WhatsApp par apply kar sakte hain, ya kiosk.eko.in par \"Apply Now\" mein apni jaankari bharein. Hamari team 24 ghante ke andar aapse sampark karti hai.",
            "en": "You can apply right here on WhatsApp, or fill in your details under \"Apply Now\" on kiosk.eko.in. Our team gets in touch within 24 hours.",
            "hi": "आप यहीं WhatsApp पर अप्लाई कर सकते हैं, या kiosk.eko.in पर \"Apply Now\" में अपनी जानकारी भरें। हमारी टीम 24 घंटे के अंदर आपसे संपर्क करती है।",
            "gu": "તમે અહીં જ WhatsApp પર અરજી કરી શકો છો, અથવા kiosk.eko.in પર \"Apply Now\"માં તમારી માહિતી ભરો. અમારી ટીમ 24 કલાકમાં તમારો સંપર્ક કરે છે.",
            "pa": "ਤੁਸੀਂ ਇੱਥੇ ਹੀ WhatsApp 'ਤੇ ਅਪਲਾਈ ਕਰ ਸਕਦੇ ਹੋ, ਜਾਂ kiosk.eko.in 'ਤੇ \"Apply Now\" ਵਿੱਚ ਆਪਣੀ ਜਾਣਕਾਰੀ ਭਰੋ। ਸਾਡੀ ਟੀਮ 24 ਘੰਟਿਆਂ ਵਿੱਚ ਤੁਹਾਡੇ ਨਾਲ ਸੰਪਰਕ ਕਰਦੀ ਹੈ।",
        },
    },
    {
        "id": "operator_role", "question": "Kiosk Operator ka kaam kya hai?", "source": "kiosk.eko.in",
        "keys": ["operator ka kaam", "operator kya karta", "csp ka kaam", "role kya", "zimmedari", "jimmedari",
                 "responsibility", "doorstep", "ghar ghar", "जिम्मेदारी", "ऑपरेटर का काम", "જવાબદારી", "ਜ਼ਿੰਮੇਵਾਰੀ"],
        "answer": {
            "hinglish": "Aap apne ilaake ka banking saathi bante hain: logon ke khate kholna, paise jama-nikaalna, transfer, yojanaon mein enrolment, aur insurance, RD, loan ke leads dena. Aap ghar-ghar jaakar bhi banking de sakte hain, aur kisi ki shikayat ho to link branch se milkar use suljhate hain. Eko devices, training, certificate aur lagataar support deta hai.",
            "en": "You become your area's banking partner: opening accounts, deposits and withdrawals, transfers, scheme enrolments, and leads for insurance, RD and loans. You can also take banking to people's doorsteps, and you own a customer's complaint, working it out with the link branch. Eko provides the devices, training, certification and ongoing support.",
            "hi": "आप अपने इलाके के बैंकिंग साथी बनते हैं: लोगों के खाते खोलना, पैसे जमा-निकालना, ट्रांसफर, योजनाओं में नामांकन, और इंश्योरेंस, RD, लोन के लीड देना। आप घर-घर जाकर भी बैंकिंग दे सकते हैं, और किसी की शिकायत हो तो लिंक ब्रांच से मिलकर उसे सुलझाते हैं। Eko डिवाइस, ट्रेनिंग, सर्टिफ़िकेट और लगातार सपोर्ट देता है।",
            "gu": "તમે તમારા વિસ્તારના બેંકિંગ સાથી બનો છો: લોકોનાં ખાતાં ખોલવાં, પૈસા જમા-ઉપાડ, ટ્રાન્સફર, યોજનાઓમાં નોંધણી, અને વીમા, RD, લોનના લીડ આપવા. તમે ઘરે-ઘરે જઈને પણ બેંકિંગ આપી શકો છો, અને કોઈની ફરિયાદ હોય તો લિંક બ્રાન્ચ સાથે મળીને ઉકેલો છો. Eko ડિવાઇસ, તાલીમ, સર્ટિફિકેટ અને સતત સપોર્ટ આપે છે.",
            "pa": "ਤੁਸੀਂ ਆਪਣੇ ਇਲਾਕੇ ਦੇ ਬੈਂਕਿੰਗ ਸਾਥੀ ਬਣਦੇ ਹੋ: ਲੋਕਾਂ ਦੇ ਖਾਤੇ ਖੋਲ੍ਹਣਾ, ਪੈਸੇ ਜਮ੍ਹਾਂ-ਕਢਵਾਉਣਾ, ਟ੍ਰਾਂਸਫਰ, ਯੋਜਨਾਵਾਂ ਵਿੱਚ ਨਾਮਾਂਕਣ, ਅਤੇ ਬੀਮਾ, RD, ਲੋਨ ਦੇ ਲੀਡ ਦੇਣਾ। ਤੁਸੀਂ ਘਰ-ਘਰ ਜਾ ਕੇ ਵੀ ਬੈਂਕਿੰਗ ਦੇ ਸਕਦੇ ਹੋ, ਅਤੇ ਕਿਸੇ ਦੀ ਸ਼ਿਕਾਇਤ ਹੋਵੇ ਤਾਂ ਲਿੰਕ ਬ੍ਰਾਂਚ ਨਾਲ ਮਿਲ ਕੇ ਉਸਨੂੰ ਸੁਲਝਾਉਂਦੇ ਹੋ। Eko ਡਿਵਾਈਸ, ਟ੍ਰੇਨਿੰਗ, ਸਰਟੀਫਿਕੇਟ ਅਤੇ ਲਗਾਤਾਰ ਸਪੋਰਟ ਦਿੰਦਾ ਹੈ।",
        },
    },
]

# What the site adds to answers the Creator Pack already gives: said after
# them, so the confirmed answer still comes first.
SITE_ADDS: Dict[str, Dict[str, str]] = {
    "earnings": {
        "hinglish": "Eko ki site ke hisaab se kamaai ₹15,000 se ₹1 lakh+ mahina tak ho sakti hai: banking commission plus PMSBY, PMJJBY, APY jaisi yojanaon ka incentive, seedha aapke SBI khate mein. Eko ke top 10 CSP ka average commission lagbhag ₹33,768 mahina hai (AePS se ₹17,672, balance se ₹5,520, money transfer se ₹4,100, rural incentive ₹1,600 aur baaki), lekin zyadatar CSP isse kaafi kam kamaate hain.",
        "en": "Per Eko's site, earnings can range from ₹15,000 to ₹1 lakh+ a month: banking commission plus incentives for schemes such as PMSBY, PMJJBY and APY, paid straight into your SBI account. Eko's top 10 CSPs average about ₹33,768 a month in commission (₹17,672 from AePS, ₹5,520 from balances, ₹4,100 from money transfers, a ₹1,600 rural incentive and the rest), but most CSPs earn considerably less.",
        "hi": "Eko की साइट के अनुसार कमाई ₹15,000 से ₹1 लाख+ महीना तक हो सकती है: बैंकिंग कमीशन और PMSBY, PMJJBY, APY जैसी योजनाओं का इंसेंटिव, सीधे आपके SBI खाते में। Eko के टॉप 10 CSP का औसत कमीशन लगभग ₹33,768 महीना है (AePS से ₹17,672, बैलेंस से ₹5,520, मनी ट्रांसफर से ₹4,100, रूरल इंसेंटिव ₹1,600 और बाकी), लेकिन ज़्यादातर CSP इससे काफ़ी कम कमाते हैं।",
        "gu": "Ekoની સાઇટ મુજબ કમાણી મહિને ₹15,000થી ₹1 લાખ+ સુધી થઈ શકે છે: બેંકિંગ કમિશન અને PMSBY, PMJJBY, APY જેવી યોજનાઓનો ઇન્સેન્ટિવ, સીધો તમારા SBI ખાતામાં. Ekoના ટોપ 10 CSPનું સરેરાશ કમિશન મહિને લગભગ ₹33,768 છે (AePSથી ₹17,672, બેલેન્સથી ₹5,520, મની ટ્રાન્સફરથી ₹4,100, રૂરલ ઇન્સેન્ટિવ ₹1,600 અને બાકી), પણ મોટાભાગના CSP આનાથી ઘણું ઓછું કમાય છે.",
        "pa": "Eko ਦੀ ਸਾਈਟ ਮੁਤਾਬਕ ਕਮਾਈ ₹15,000 ਤੋਂ ₹1 ਲੱਖ+ ਮਹੀਨਾ ਤੱਕ ਹੋ ਸਕਦੀ ਹੈ: ਬੈਂਕਿੰਗ ਕਮਿਸ਼ਨ ਅਤੇ PMSBY, PMJJBY, APY ਵਰਗੀਆਂ ਯੋਜਨਾਵਾਂ ਦਾ ਇੰਸੈਂਟਿਵ, ਸਿੱਧਾ ਤੁਹਾਡੇ SBI ਖਾਤੇ ਵਿੱਚ। Eko ਦੇ ਟਾਪ 10 CSP ਦਾ ਔਸਤ ਕਮਿਸ਼ਨ ਲਗਭਗ ₹33,768 ਮਹੀਨਾ ਹੈ (AePS ਤੋਂ ₹17,672, ਬੈਲੇਂਸ ਤੋਂ ₹5,520, ਮਨੀ ਟ੍ਰਾਂਸਫਰ ਤੋਂ ₹4,100, ਰੂਰਲ ਇੰਸੈਂਟਿਵ ₹1,600 ਅਤੇ ਬਾਕੀ), ਪਰ ਜ਼ਿਆਦਾਤਰ CSP ਇਸ ਤੋਂ ਕਾਫ਼ੀ ਘੱਟ ਕਮਾਉਂਦੇ ਹਨ।",
    },
    "women": {
        "hinglish": "Eko ki site ke hisaab se mahila CSP ko 10% zyada commission milta hai. Ghar ke paas kaam, apne naam se kamaai, apni banking aur credit history, ilaake mein apni pehchaan, aur zaroorat par call karne ke liye ek coordinator.",
        "en": "Per Eko's site, women CSPs earn 10% higher commission. They work close to home, earn in their own name, build their own banking and credit history and standing in the community, and have a coordinator to call.",
        "hi": "Eko की साइट के अनुसार महिला CSP को 10% ज़्यादा कमीशन मिलता है। घर के पास काम, अपने नाम से कमाई, अपनी बैंकिंग और क्रेडिट हिस्ट्री, इलाके में अपनी पहचान, और ज़रूरत पर कॉल करने के लिए एक कोऑर्डिनेटर।",
        "gu": "Ekoની સાઇટ મુજબ મહિલા CSPને 10% વધુ કમિશન મળે છે. ઘરની નજીક કામ, પોતાના નામે કમાણી, પોતાની બેંકિંગ અને ક્રેડિટ હિસ્ટ્રી, વિસ્તારમાં પોતાની ઓળખ, અને જરૂર પડે ત્યારે ફોન કરવા માટે એક કોઓર્ડિનેટર.",
        "pa": "Eko ਦੀ ਸਾਈਟ ਮੁਤਾਬਕ ਮਹਿਲਾ CSP ਨੂੰ 10% ਵੱਧ ਕਮਿਸ਼ਨ ਮਿਲਦਾ ਹੈ। ਘਰ ਦੇ ਨੇੜੇ ਕੰਮ, ਆਪਣੇ ਨਾਮ 'ਤੇ ਕਮਾਈ, ਆਪਣੀ ਬੈਂਕਿੰਗ ਅਤੇ ਕ੍ਰੈਡਿਟ ਹਿਸਟਰੀ, ਇਲਾਕੇ ਵਿੱਚ ਆਪਣੀ ਪਛਾਣ, ਅਤੇ ਲੋੜ ਪੈਣ 'ਤੇ ਕਾਲ ਕਰਨ ਲਈ ਇੱਕ ਕੋਆਰਡੀਨੇਟਰ।",
    },
    "real": {
        "hinglish": "17+ saal ka bharosa: Eko SBI ke sabse achhe Business Correspondents mein gina jaata hai, aur 1,100+ CSP 160+ districts mein kaam kar rahe hain.",
        "en": "17+ years of trust: Eko is ranked among SBI's best Business Correspondents, with 1,100+ CSPs in 160+ districts.",
        "hi": "17+ साल का भरोसा: Eko, SBI के सबसे अच्छे बिज़नेस कॉरेस्पॉन्डेंट्स में गिना जाता है, और 1,100+ CSP 160+ ज़िलों में काम कर रहे हैं।",
        "gu": "17+ વર્ષનો ભરોસો: Eko, SBIના શ્રેષ્ઠ બિઝનેસ કૉરસ્પોન્ડન્ટ્સમાં ગણાય છે, અને 1,100+ CSP 160+ જિલ્લાઓમાં કામ કરે છે.",
        "pa": "17+ ਸਾਲ ਦਾ ਭਰੋਸਾ: Eko, SBI ਦੇ ਸਭ ਤੋਂ ਵਧੀਆ ਬਿਜ਼ਨਸ ਕੋਰੈਸਪੋਂਡੈਂਟਾਂ ਵਿੱਚ ਗਿਣਿਆ ਜਾਂਦਾ ਹੈ, ਅਤੇ 1,100+ CSP 160+ ਜ਼ਿਲ੍ਹਿਆਂ ਵਿੱਚ ਕੰਮ ਕਰ ਰਹੇ ਹਨ।",
    },
    "training": {
        "hinglish": "Training digital hai, Hindi mein: financial literacy, CRM, compliance, risk aur audit. IIBF aur DRA certification onboarding ke 9 mahine ke andar poora hota hai.",
        "en": "Training is digital, in Hindi: financial literacy, CRM, compliance, risk and audit. IIBF and DRA certification is completed within 9 months of onboarding.",
        "hi": "ट्रेनिंग डिजिटल है, हिंदी में: फाइनेंशियल लिटरेसी, CRM, कंप्लायंस, रिस्क और ऑडिट। IIBF और DRA सर्टिफ़िकेशन ऑनबोर्डिंग के 9 महीने के अंदर पूरा होता है।",
        "gu": "તાલીમ ડિજિટલ છે, હિન્દીમાં: ફાઇનાન્શિયલ લિટરસી, CRM, કમ્પ્લાયન્સ, રિસ્ક અને ઓડિટ. IIBF અને DRA સર્ટિફિકેશન ઓનબોર્ડિંગના 9 મહિનામાં પૂરું થાય છે.",
        "pa": "ਟ੍ਰੇਨਿੰਗ ਡਿਜੀਟਲ ਹੈ, ਹਿੰਦੀ ਵਿੱਚ: ਫਾਇਨੈਂਸ਼ੀਅਲ ਲਿਟਰੇਸੀ, CRM, ਕੰਪਲਾਇੰਸ, ਰਿਸਕ ਅਤੇ ਆਡਿਟ। IIBF ਅਤੇ DRA ਸਰਟੀਫਿਕੇਸ਼ਨ ਆਨਬੋਰਡਿੰਗ ਦੇ 9 ਮਹੀਨਿਆਂ ਵਿੱਚ ਪੂਰਾ ਹੁੰਦਾ ਹੈ।",
    },
    "devices": {
        "hinglish": "Eko devices aur kiosk ki branding deliver karke set up karta hai: laptop, passbook printer, Micro-ATM, biometric scanner.",
        "en": "Eko delivers and sets up the devices and the kiosk branding: laptop, passbook printer, Micro-ATM and biometric scanner.",
        "hi": "Eko डिवाइस और कियोस्क की ब्रांडिंग डिलीवर करके सेट अप करता है: लैपटॉप, पासबुक प्रिंटर, माइक्रो-ATM, बायोमेट्रिक स्कैनर।",
        "gu": "Eko ડિવાઇસ અને કિઓસ્કની બ્રાન્ડિંગ પહોંચાડીને સેટ અપ કરે છે: લેપટોપ, પાસબુક પ્રિન્ટર, માઇક્રો-ATM, બાયોમેટ્રિક સ્કેનર.",
        "pa": "Eko ਡਿਵਾਈਸ ਅਤੇ ਕਿਓਸਕ ਦੀ ਬ੍ਰਾਂਡਿੰਗ ਪਹੁੰਚਾ ਕੇ ਸੈੱਟ ਅੱਪ ਕਰਦਾ ਹੈ: ਲੈਪਟਾਪ, ਪਾਸਬੁੱਕ ਪ੍ਰਿੰਟਰ, ਮਾਈਕ੍ਰੋ-ATM, ਬਾਇਓਮੈਟ੍ਰਿਕ ਸਕੈਨਰ।",
    },
}
for _f in FAQ:
    # The Creator Pack's own words stay for the template agents, who must not quote figures.
    _f["pack_answer"] = dict(_f["answer"])
    for _lang, _extra in SITE_ADDS.get(_f["id"], {}).items():
        _f["answer"][_lang] = f"{_f['answer'][_lang]} {_extra}"

FAQ = FAQ + SITE_FAQ

# Other ways people ask the same thing (2026-10-18: the team wants the bot to
# understand a question however it is put, not only in the FAQ's words). The
# spelling and the script do not need listing: "naukari", "नौकरी" and "ਨੌਕਰੀ"
# all match "naukri" by sound (see _sound). Only new words and phrasings go here.
MORE_KEYS: Dict[str, List[str]] = {
    "job": ["bank kaam milega", "bank kaam", "bank naukri milegi", "बैंक नौकरी मिलेगी", "बैंक काम", "employee", "bank employee", "bank ka employee", "bank ka staff", "karmachari", "bank mein naukri",
            "bank me job", "permanent", "joining", "recruitment", "bharti", "sarkari naukri",
            "kya main bank ka", "bank wala ban", "मुलाजिम", "कर्मचारी", "નોકરિયાત", "ਮੁਲਾਜ਼ਮ"],
    "real": ["aap sahi ho", "sahi ho", "paise le liye", "thag liya", "thage gaye", "fraud hua", "dhokha hua", "sach", "sacha", "sachcha", "bharosa", "vishwas", "trust", "scam", "dhokha", "thagi", "nakli", "legit",
             "authorized", "authorised", "registered company", "sahi company", "eko kya hai", "eko company", "eko kya company", "kaun si company", "company ka naam",
             "विश्वास", "नकली", "ठगी", "ભરોસો", "ਭਰੋਸਾ"],
    "fees": ["form ka charge", "bharne ka charge", "form bharne ka charge", "koi charge", "apply ka charge", "fees lagegi", "kitni fees", "form fees", "charge lagega", "registration fees", "apply free",
             "free hai", "mufat", "muft", "paise lagenge apply", "मुफ्त", "ફ્રી", "ਮੁਫ਼ਤ"],
    "investment": ["paise ka kya", "paise ka scene", "paisa ka kya", "bina paisa", "bina invest", "zero investment", "paisa lagega", "paisa lagana", "kuch paisa", "paisa dena", "kuch invest", "invest karna",
                   "lagat lagegi", "kharcha lagega", "kharcha hoga", "paisa chahiye hoga", "पैसा लगेगा", "पैसे लगेंगे",
                   "નાણાં લાગશે", "ਪੈਸਾ ਲੱਗੇਗਾ", "paisa kitna dena", "kitna dena hoga", "kitna paisa dena", "how much money", "money need", "need to start", "kitne paise dene", "शुरू करने के लिए कितना", "kitna lagana", "kitna lagega", "paise lagane", "paisa lagana", "lagana padega", "cost",
                   "budget", "capital", "amount lagega", "kitne rupaye", "kitna kharch", "5 lac", "पैसे लगाने",
                   "कितना लगेगा", "કેટલા પૈસા", "ਕਿੰਨੇ ਪੈਸੇ"],
    "devices": ["saman", "samaan", "equipment", "atm machine", "fingerprint", "thumb machine", "passbook machine",
                "kya kya milega", "setup", "सामान", "સામાન", "ਸਮਾਨ"],
    "with_shop": ["dukan", "shop", "kahan baithna", "jagah chahiye", "counter", "ghar se chala",
                  "ghar par chala", "kitne baje", "kitne ghante", "દુકાનમાં"],
    "training": ["sikhayega", "kaun sikhaye", "kaun sikhayega", "sikhaoge", "sikha denge", "kuch nahi aata", "nahi aata", "computer nahi aata", "सिखाओगे", "नहीं आता", "sikhaenge", "sikhna", "seekhna", "pariksha", "test dena", "kaise sikhe",
                 "सीखना", "परीक्षा", "શીખવું", "ਸਿੱਖਣਾ"],
    "family": ["bete ke naam", "beti ke naam", "pati ke naam", "bhai ke naam", "papa ke naam", "ke naam pe le sakte", "बेटे के नाम", "ghar wale", "gharwale", "beta chala", "wife chala", "koi aur chala", "relative", "rishtedar",
               "साथ में", "ઘરના", "ਘਰਵਾਲੇ"],
    "earnings": ["kama lete", "kitna kama lete", "ghar chal jayega", "kamai kaisi", "kamai kaisi hai", "हर महीने कितना", "कितना मिलेगा", "mahine kitna milega", "kitna milega mahine", "kitna nikal", "kitna bachega", "kitna kamaa", "kitna kama", "kitni kamai", "kitne paise milenge", "kitna paisa milega",
                 "fayda", "faida", "labh", "earn", "how much earn", "income kitni", "mahine ka kitna", "monthly kitna", "kitna banega",
                 "फायदा", "लाभ", "ફાયદો", "ਫ਼ਾਇਦਾ"],
    "salary": ["salary kitni", "salary milegi", "kitni salary", "fix paisa", "fixed income", "har mahine fix", "pakka paisa", "guaranteed income", "guarantee income", "income guarantee", "garanti",
               "fix milega", "पक्का", "ગેરંટી", "ਪੱਕਾ"],
    "women": ["wife ke naam", "patni ke naam", "biwi ke naam", "mahila ke naam", "ghar pe rehti", "housewife ke naam",
              "mahilaon", "ladki", "aurto", "auraton", "beti chala", "lady operator", "स्त्री", "ਔਰਤਾਂ"],
    # Not "chutti" or "holiday": "aaj chutti hai?" asks whether we are open, not about the penalty.
    "penalty": ["band rakhu", "band rakhe", "kuch din band", "band rakha", "band kar diya", "lambe samay band", "kitne din band"],
    "eligibility": ["10th fail", "12th fail", "fail hun", "kya shart hai", "12th tak", "meri padhai", "padhai kitni chahiye", "kitna padha", "mil sakta hai kya mujhe", "12th pass", "10th pass", "kar sakta hun", "kar sakti hun", "kar sakta hoon", "kar sakti hoon", "main kar sakta", "graduate hun", "12वीं पास", "कर सकता हूँ", "kaun ban sakta", "main ban sakta", "kya main apply", "kya mai apply", "can i apply",
                    "qualification", "padhai kitni", "kitna padha", "umar", "age limit", "yogya hun",
                    "उम्र", "आयु", "ઉંમર", "ਉਮਰ"],
    "cibil": ["credit report", "loan chal raha", "loan liya", "emi", "default", "credit history", "सिबिल स्कोर"],
    "documents": ["kya kya chahiye hoga", "apply karne ke liye kya", "kya kya lagega", "kya lagega", "proof", "kagzat", "papers chahiye", "aadhar", "aadhaar", "pan card",
                  "police", "certificate chahiye", "कागजात", "આધાર", "ਆਧਾਰ"],
    "commission_paid": ["kab tak aata", "kab aata hai", "commission kab tak", "kab credit hota", "paisa kab aayega", "kab tak milega paisa", "payment date", "kis tareekh", "tarikh",
                        "account mein kab", "kab credit", "कब मिलेगा", "ક્યારે મળશે", "ਕਦੋਂ ਮਿਲੇਗਾ"],
    "process": ["csp lena hai", "csp chahiye", "mini bank kholna", "bank kholna hai", "process batao", "lene ke liye kya karna", "kya karna padega", "judna hai", "judna chahta", "judna chahti", "jodna hai",
                "how can i start", "start a csp", "start csp", "start an sbi csp", "csp kaise milega", "csp milega kaise",
                "apply kaise", "apply kaise kar", "apply karna hai", "csp ban", "kiosk operator ban", "operator ban", "kiosk ban", "csp kaise",
                "csp kholna", "kiosk kholna", "csp kaise milega", "how do i become", "how to become", "become kiosk operator",
                "become csp", "become a csp", "join eko", "eko ke saath judna", "eko ke saath kaam", "sbi csp", "सीएसपी कैसे",
                "कियोस्क ऑपरेटर कैसे", "કેવી રીતે બની", "ਕਿਵੇਂ ਬਣ", "aage kya karna", "kya karna hai aage", "ab kya karna", "kitne din", "kab shuru", "shuru ho jayega", "kab tak chalu", "कितने दिन", "आगे क्या करना", "aage kya karna", "aage kya", "next step", "shuru kaise", "kaise judein", "kaise jude", "kaise apply",
                "how to apply", "kitne din lagenge", "kitna time lagega", "kab tak shuru", "जुड़ना", "शुरू कैसे"],
    "services": ["kaun kaun si services", "services de sakte", "kya services de", "kaun si services", "paise nikal sakte", "paise nikal", "nikal sakte", "jama kar sakte", "kya kya kar sakte log", "पैसे निकाल सकते", "kya kya kaam", "kya services", "kaun kaun se kaam", "account kholna", "cash withdrawal", "पैसे निकालना", "खाता खोलना"],
    "setup_cost": ["machine ka kharcha", "kharcha kaun dega", "device ka paisa kaun", "machine kaun dega", "मशीन का खर्चा"],
    "schemes": ["bima", "insurance", "beema", "बीमा", "વીમો", "ਬੀਮਾ"],
    "what_csp": ["csp matlab", "csp meaning", "csp means", "csp arth", "csp kise kehte", "csp kya cheez", "kiosk matlab",
                 "kiosk meaning", "banking outlet matlab", "customer service point matlab", "सीएसपी मतलब", "सीएसपी अर्थ",
                 "csp मतलब", "સીએસપી એટલે", "ਸੀਐਸਪੀ ਮਤਲਬ"],
    "reach": ["kahan kahan hai", "kis state", "kitne state", "kitne log", "kitne kiosk", "network", "हर जगह"],
}
for _f in FAQ:
    _f["keys"] = list(dict.fromkeys(_f["keys"] + MORE_KEYS.get(_f["id"], [])))

# Some words belong to more than one question ("fixed salary" names the
# salary question, not the job one); the longer, more specific key wins.
_BY_ID = {f["id"]: f for f in FAQ}
_LATIN = re.compile(r"[A-Za-z]")


def _norm(text: str) -> str:
    return " " + re.sub(r"[^\wऀ-෿₹]+", " ", (text or "").lower()) + " "


# --- Matching by sound --------------------------------------------------------
# People write the same word many ways: "naukri", "naukari", "nokri", and in
# Devanagari, Gurmukhi or Gujarati. Each word is reduced to the consonants it
# is said with, in Latin letters: all of those become "nkr". The Indic scripts
# share one layout, so Gurmukhi and Gujarati letters are read as Devanagari's.
_INDIC_BASES = (0x0980, 0x0A00, 0x0A80, 0x0B00, 0x0C00, 0x0C80, 0x0D00)
_DEVA = {
    "क": "k", "ख": "k", "ग": "g", "घ": "g", "ङ": "n", "च": "c", "छ": "c", "ज": "j", "झ": "j", "ञ": "n",
    "ट": "t", "ठ": "t", "ड": "d", "ढ": "d", "ण": "n", "त": "t", "थ": "t", "द": "d", "ध": "d", "न": "n",
    "प": "p", "फ": "f", "ब": "b", "भ": "b", "म": "m", "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "s", "ष": "s", "स": "s", "ह": "h", "ं": "n", "ँ": "n", "ॐ": "m",
    "क़": "k", "ख़": "k", "ग़": "g", "ज़": "j", "ड़": "r", "ढ़": "r", "फ़": "f", "य़": "y",
}
_DEVA_VOWELS = set("अआइईउऊऋएऐओऔ")
_LATIN_FOLD = [("chh", "c"), ("ch", "c"), ("kh", "k"), ("gh", "g"), ("jh", "j"), ("th", "t"), ("dh", "d"),
               ("ph", "f"), ("bh", "b"), ("sh", "s"), ("ck", "k"), ("q", "k"), ("x", "ks"), ("z", "j"), ("w", "v")]


def _devanagari(ch: str) -> str:
    code = ord(ch)
    for base in _INDIC_BASES:
        if base <= code < base + 0x80:
            return chr(0x0900 + code - base)
    return ch


def _sound(word: str) -> str:
    """The consonants a word is said with, in Latin letters: naukri, naukari, नौकरी, ਨੌਕਰੀ -> nkr."""
    word = "".join(_devanagari(c) for c in word.lower())
    out = []
    if re.search(r"[ऀ-ॿ]", word):
        for i, c in enumerate(word):
            if c in _DEVA:
                out.append(_DEVA[c])
            elif c in _DEVA_VOWELS and i == 0:
                out.append("a")
            elif c.isascii() and c.isalnum():
                out.append(c)
    else:
        w = word
        for a, b in _LATIN_FOLD:
            w = w.replace(a, b)
        for i, c in enumerate(w):
            if c in "aeiou":
                if i == 0:
                    out.append("a")
            elif c.isalnum():
                out.append(c)
    s = "".join(out)
    # A y or h inside a word comes and goes with spelling (kamai/kamayi,
    # pahle/pehle); one at the end is kept, so "tankhah" is not "thank".
    s = s[:1] + re.sub(r"[yh]", "", s[1:-1]) + s[-1:] if len(s) > 2 else s
    return re.sub(r"(.)\1+", r"\1", s)


_VOWEL_SIGNS = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "e", "ो": "o", "ौ": "o",
                "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "e", "ओ": "o", "औ": "o"}


def _vowels(word: str) -> str:
    """The vowel signs of an Indic word, read through Devanagari: नौकरी and નોકરી -> "oi"."""
    return "".join(_VOWEL_SIGNS.get(_devanagari(c), "") for c in word)


# The many ways short, common Hinglish words are typed, read as one: too short
# to be matched by sound ("kese" and "kaise" are both "ks"), and in every question.
_SAME_WORD = {
    "kaise": ("kese", "kaisey", "kaese", "kesy", "kaisay", "kase", "kese", "kesay", "kaisa", "kesa", "kaisi", "kesi"),
    "kya": ("kia", "kyaa", "kyà", "kiya"),
    "nahi": ("nhi", "nahin", "nai", "nhin", "nahee", "nahi"),
    "ban": ("bane", "banu", "banoon", "banun", "banna", "bano", "banne", "bnu", "banunga", "banungi", "banenge",
            "banega", "banegi", "banta", "banti", "banate", "bnna", "bnne"),
    "sakta": ("sakti", "sakte", "skta", "skti", "skte", "sakhta", "sakhti", "sakoon", "saku", "sakun", "sakenge"),
    "hun": ("hoon", "hu", "hoo", "hn"),
    "karna": ("krna", "karni", "krni", "karne", "krne"),
    "milega": ("milegi", "milenge", "milta", "milti", "milte", "milega", "mlega", "milegaa"),
    "chahiye": ("chahie", "chaiye", "chahiyea", "chahye", "chaiya", "chahiya"),
    "paisa": ("paise", "pese", "paisay", "paisa", "pesa", "paiso"),
    "lena": ("leni", "lene", "lu", "loon", "lun"),
    "kholna": ("kholni", "kholne", "kholu", "kholun", "kholoon"),
}
_CANON = {v: k for k, vs in _SAME_WORD.items() for v in vs}


def _words(text: str) -> List[str]:
    # Indic vowel signs are not \w, so the Indic blocks are named whole: "ફોર્મ" is one word, not three.
    return [_CANON.get(w, w) for w in re.findall(r"[\wऀ-෿₹]+", (text or "").lower())]


def _close(a: str, b: str) -> bool:
    """Two spellings in Latin letters near enough to be one word: naukari/naukri, commison/commission."""
    if abs(len(a) - len(b)) > 2:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= max(1, min(len(a), len(b)) // 4)


def _same(p: str, w: str, s: str) -> bool:
    """A key word and a word said are one: the same, or the same sound (and, in Latin letters, a close spelling)."""
    if p == w:
        return True
    k = _sound(p)
    if len(k) < 3 or k != s:
        return False
    latin_p, latin_w = bool(_LATIN.search(p)), bool(_LATIN.search(w))
    # Both in Latin letters: the spellings must be close too, so "Shivani"
    # is not "sevayein". Both Indic: the sound, read through one layout, so
    # Gujarati "નોકરી" is Hindi "नौकरी". Latin against Indic: three consonants
    # are too few to be sure ("store" is not "स्त्री"), so only longer words.
    if latin_p and latin_w:
        return _close(p, w)
    if latin_p != latin_w:
        return len(k) >= 5
    # Both Indic: the vowel signs must agree too ("सीखना" is not "स्कैन").
    return _vowels(p) == _vowels(w)


# Keys that only name the subject ("SBI CSP", "CSP kholna"): nearly every
# question has them, so they tell the process question from the rest only
# when nothing else is asked. "CSP kholne ke liye paisa lagega?" is about money.
SUBJECT_KEYS = {"sbi csp", "csp kholna", "kiosk kholna", "join eko", "eko ke saath judna", "eko ke saath kaam",
                "csp kaise",
                # Said in every second question: "kya kya" asks nothing by itself.
                "kya kya"}

# Single words with more than one meaning ("school fees", "padhai ka kharcha",
# "EMI bhar paunga"): alone they are not enough to answer; with another sign
# of the question ("apply ki fees", "kitni fees", "CSP ka kharcha") they are.
LOOSE_KEYS = {"fee", "fees", "kharcha", "lagat", "emi", "loan", "charges", "charge", "cost", "budget", "amount",
              "default", "photo", "machine", "computer", "time", "salary", "fixed", "certificate", "exam", "course",
              "फीस", "खर्चा", "लागत", "ફી", "ખર્ચ", "ਫੀਸ", "ਖਰਚਾ"}

# Words that ask (not "kya", which is in everything): with one of these, a
# loose word does count ("fees kitni hai", "kaun si machine milegi").
_ASKING = ("kitna", "kitni", "kitne", "kaun", "kaunsi", "konsi", "kon si", "kaun si", "chahiye", "lagega", "lagegi",
           "lagenge", "lagta", "lagti", "dena padega", "lena padega", "dena hoga", "lena hoga", "milega", "kab",
           "how much", "what", "which", "need", "कितना", "कितनी", "कितने", "कौन", "चाहिए", "लगेगा", "ਕਿੰਨਾ", "ਕਿੰਨੀ",
           "ਕਿਹੜੀ", "ਚਾਹੀਦਾ", "કેટલું", "કેટલી", "કયા", "જોઈએ")

# Words allowed between two words of a key: "csp ka kya matlab" still says "csp matlab".
GAP = 2


def _where(key: str, words: List[str], sounds: List[str]) -> Optional[frozenset]:
    """
    The positions of the words a key matches in the message, or None if it does not.

    The key's words must come in order, with at most GAP other words between
    two of them, so a question put in its own words still finds the key.
    """
    parts = _words(key)
    if not parts:
        return None
    indic = not _LATIN.search(key)

    def same(p: str, i: int) -> bool:
        # An Indic key may carry a suffix in the message ("सेवा" in "सेवाएँ").
        return _same(p, words[i], sounds[i]) or (indic and p in words[i])

    def follow(j: int, start: int, at: tuple) -> Optional[tuple]:
        if j == len(parts):
            return at
        for i in range(start, min(len(words), start + GAP + 1)):
            if same(parts[j], i):
                found = follow(j + 1, i + 1, at + (i,))
                if found:
                    return found
        return None

    for i in range(len(words)):
        if same(parts[0], i):
            found = follow(1, i + 1, (i,))
            if found:
                return frozenset(found)
    return None


# Words of a complaint from someone already running a CSP ("AEPS me error aa
# raha hai", "paisa nahi aaya", "machine kaam nahi kar rahi"): the team's to
# answer, so no FAQ answer is given even when the FAQ's words are in it.
_COMPLAINT = ("bhej diye", "bhej diya", "bhej di", "submit kar diya", "jama kar diya", "error", "kaam nahi kar", "nahi chal raha", "nahi chal rahi", "nahi aaya", "nahi aa raha", "nahi ho raha",
              "problem", "issue", "band ho gaya", "band ho gayi", "fail ho gaya", "fail ho gayi", "failed", "transaction fail", "not working", "complaint",
              "shikayat", "atak gaya", "atka hua", "nahi mila", "काम नहीं", "नहीं आया", "समस्या", "शिकायत", "ਕੰਮ ਨਹੀਂ",
              "કામ નથી")


def is_complaint(text: str) -> bool:
    said = " " + " ".join(_words(text)) + " "
    return any(f" {' '.join(_words(c))} " in said for c in _COMPLAINT)


def match(text: str, limit: int = 2) -> List[str]:
    """
    The FAQ entries a message asks about, best first; empty when none fits.

    A key matches its words said in order, spelt or written in any script.
    The same words are counted once for an entry, so a question naming
    "commission" is not counted twice for the Hindi and the English key.
    """
    if is_complaint(text):
        return []
    words = _words(text)
    sounds = [_sound(w) for w in words]
    # Does the message ask something ("kitni", "kaun si", "chahiye", "lagega")?
    said = " " + " ".join(words) + " "
    asks = any(f" {' '.join(_words(q))} " in said for q in _ASKING)
    scores: Dict[str, float] = {}
    for f in FAQ:
        hits = []
        for key in f["keys"]:
            at = _where(key, words, sounds)
            if at is not None:
                k = _norm(key).strip()
                loose = k in LOOSE_KEYS and not asks
                weight = 0.3 if k in SUBJECT_KEYS else 0.6 if loose else 1 + len(k) / 20
                # Words spread out with others between them are a weaker sign than words side by side.
                if max(at) - min(at) + 1 > len(at):
                    weight *= 0.7
                hits.append((weight, at))
        covered, score = set(), 0.0
        for weight, at in sorted(hits, key=lambda h: -h[0]):
            if not at <= covered:
                score += weight
                covered |= at
        # Only the subject named ("SBI CSP") asks nothing: no answer from that alone.
        if score >= 0.9:
            scores[f["id"]] = score
    ranked = sorted(scores, key=lambda i: -scores[i])
    # A second answer only when it is about as strong as the first.
    if len(ranked) > 1 and scores[ranked[1]] < scores[ranked[0]] * 0.6:
        ranked = ranked[:1]
    if not ranked:
        taught = _taught(words, sounds)
        if taught:
            return [taught]
    return ranked[:limit]


# --- What the team has taught the bot -----------------------------------------
# A question the bot left for a person, that the team says one of these answers
# covers ("Teach the bot" in the inbox). Kept in app_settings (faq_learning), and
# a later question saying nearly the same thing gets that answer. Filled at
# startup and on every teaching by faq_learning.load.
LEARNED: Dict[str, List[str]] = {}

# Words every question has, which say nothing about what is asked.
_FILLER = {
    "kya", "kyaa", "kia", "hai", "hain", "he", "h", "ho", "hoga", "hogi", "ki", "ka", "ke", "ko", "se", "me", "mein", "mai",
    "main", "mujhe", "muje", "mera", "meri", "mere", "hum", "hame", "hamein", "aap", "ap", "aapka", "aapki", "ye", "yeh",
    "yah", "wo", "woh", "to", "toh", "bhi", "sir", "ji", "g", "sar", "madam", "please", "plz", "pls", "bhai", "namaste",
    "the", "is", "a", "an", "to", "do", "i", "of", "and", "or", "it", "this", "kaise", "kab", "kitna", "kitni", "kitne",
    "क्या", "है", "हैं", "की", "का", "के", "को", "से", "में", "मैं", "मुझे", "मेरा", "आप", "ये", "यह", "तो", "भी", "जी",
}


def _content(words: List[str], sounds: List[str]) -> List[tuple]:
    return [(w, s) for w, s in zip(words, sounds) if w not in _FILLER and not w.isdigit()]


def _taught(words: List[str], sounds: List[str]) -> Optional[str]:
    """The FAQ entry whose taught question this message nearly repeats, if one does."""
    said = _content(words, sounds)
    if len(said) < 2:
        return None
    best, best_share = None, 0.0
    for faq_id, examples in LEARNED.items():
        if faq_id not in _BY_ID:
            continue
        for example in examples:
            ew = _words(example)
            known = _content(ew, [_sound(w) for w in ew])
            if len(known) < 2:
                continue
            hit = sum(1 for p, _ in known if any(_same(p, w, s) for w, s in said))
            share = hit / max(len(known), len(said))
            if hit >= 2 and share > best_share:
                best, best_share = faq_id, share
    # Most of what is asked must be the same as what was taught.
    return best if best_share >= 0.6 else None


def answer(faq_id: str, lang: str, said: str = "") -> str:
    """One answer in the person's language: Hinglish to someone writing Hindi in Latin letters."""
    texts = _BY_ID[faq_id]["answer"]
    if lang == "hi" and said and _LATIN.search(said) and not re.search(r"[ऀ-ॿ]", said):
        return texts["hinglish"]
    if lang in texts:
        return texts[lang]
    # Marathi readers read Devanagari Hindi; other languages get English.
    return texts["hi"] if lang == "mr" else texts["en"]


def reply(faq_ids: List[str], lang: str, said: str = "") -> str:
    return "\n\n".join(answer(i, lang, said) for i in faq_ids)


# ---------------------------------------------------------------------------
# For the template agents
# ---------------------------------------------------------------------------

# The Creator Pack's word rules that do not conflict with the team's choice to
# keep SBI's name and logo, rupee figures and "franchise". (pattern, why)
AVOID = [
    (r"\b(naukri|nokri|job|jobs|vacancy|vacancies|bharti|joining)\b|नौकरी|वैकेंसी|भर्ती|નોકરી|ભરતી|ਨੌਕਰੀ|ਭਰਤੀ",
     "calls it a job; it is apna business (udyam, malik)"),
    (r"\b(salary|tankhwah|vetan|pagar)\b|सैलरी|वेतन|तनख्वाह|પગાર|ਤਨਖਾਹ",
     "promises a salary; earnings are commission and incentives"),
    (r"\b(guaranteed?|fixed (pay|income)|pakka)\b|गारंटी|गारंटीड|पक्की कमाई|ગેરંટી|ਗਾਰੰਟੀ",
     "promises guaranteed or fixed income; say commission on every service and month-on-month growth"),
    (r"zero investment|no investment|bina nivesh|limited seats?|aaj hi payment|शून्य निवेश|ज़ीरो निवेश|सीमित सीटें",
     "uses a pressure or zero-investment line; say the real investment and \"apply free\""),
    (r"\b(bank employee|bank officer|appointed|hired|mini bank|micro[- ]branch|branch manager|manager sahab)\b|मिनी बैंक|बैंक कर्मचारी",
     "makes the operator a bank employee or the outlet a branch; say Kiosk Operator, Banking Outlet"),
    (r"\bEKO\b|\beko\b", "writes Eko wrongly; it is always \"Eko\""),
]


def vocabulary_problems(text: str) -> List[str]:
    """Words from the Creator Pack's never-use list found in a piece of copy."""
    out = []
    for pattern, why in AVOID:
        found = re.search(pattern, text or "", flags=0 if "EKO" in pattern else re.IGNORECASE)
        if found:
            out.append(f"uses “{found.group(0)}”, which {why}")
    return out


PILLARS = [
    ("Pride", "becoming the area's trusted banking provider; a counter that carries a bank's name; respect from elders and officials",
     "“Poore ilaake ka banker.” “Jahan bank ka naam, wahan aapka naam.”"),
    ("Earnings", "many earning lines from day one: commission on every service, incentives on meeting goals",
     "“Kamaai ke kai raaste: khate, yojanaayein, jama, loan, bima.”"),
    ("Growth", "a clear path from setup to a profitable, lasting business, with Eko running every process for month-on-month growth",
     "“Har mahine pichhle mahine se aage. Yeh Eko ka vaada hai.”"),
]
CLOSING_LINE = "Aapki month-on-month growth, Eko ka vaada. Iske liye har process hum chalate hain."

GROWTH_PATH = [
    ("Setup", "about the first 45 days", "verification, agreement, police verification, premises and signage, devices, first training; Eko supports documents, installs devices and trains"),
    ("Start", "months 1 to 3", "opens daily, serves first customers, opens first accounts; near-daily coach calls, WhatsApp guidance, local awareness camps"),
    ("Build", "months 4 to 6", "enrols families in insurance, pension and savings schemes, gets certified; monthly reviews, scheme campaigns, certification support"),
    ("Grow", "months 7 to 12", "adds loan leads, collections, more services, meets monthly incentive goals; growth plans, product training, field visits"),
    ("Sustain", "year 2 onward", "a loyal customer base; adds family members or a second terminal; expansion support and new products"),
]

# Banking Outlet personas: (code, persona, priority, where they are, what they want,
# what stops them, pride hook, earnings hook, growth hook)
PERSONAS = [
    ("O1", "Dealer family, next generation", "A", "gas agency, 2/3-wheeler and EV dealer, car dealer, tractor and farm equipment dealer",
     "a second respected business for the next generation", "\"Our business already runs, why this?\"",
     "Papa ki agency ka naam hai. Ab poore ilaake ka banker bhi aap.", "Pension, khate, jama, bima: kamaai ke kai raaste ek counter pe.",
     "Ek aur business jo har mahine badhe. Eko ka vaada."),
    ("O2", "Agri-input and fuel family", "A", "fertiliser, seed, pesticide dealer, Kisan Samriddhi Kendra, petrol pump, Kisan Seva Kendra",
     "serve the same farmers fully; steady year-round business", "\"No time in season\"",
     "Kisan khaad ke liye bhi aapke paas, bank ke liye bhi.", "KCC, jama, bima: har seva par kamaai.",
     "Season ho ya na ho, kamaai har mahine."),
    ("O3", "Retired bank officer", "A", "bank alumni, retired staff associations, pension circles",
     "purpose, respect, using their skills", "\"A new business at this age?\"",
     "Retirement ke baad bhi log aapko bank wale sahab kehte hain.", "Aapka anubhav, kamaai ke kai raaste.",
     "Anubhav aapka, har mahine badhta business aapka."),
    ("O4", "Graduate from a business family", "A", "commerce, BBA, MBA colleges; business families",
     "ownership early, a respected standing", "\"Is it really bank work?\" \"Will the family fund it?\"",
     "24 saal ki umar, poore gaon ka bharosa.", "Doosron ke liye form bharne ke bajaye apna banking business.",
     "Har mahine badhta apna business."),
    ("O5", "Woman from an established business family", "A", "daughters and daughters-in-law in established business families",
     "her own identity and standing within the family business", "\"Home and outlet both?\"",
     "Gaon ki auratein ab apni banker se baat karti hain.", "Mahila operators ke liye atirikt incentive.",
     "Apni pehchaan, apna badhta business."),
    ("O6", "Healthcare business family", "B", "pathlab collection centre, diagnostic centre, pharmacy, Jan Aushadhi Kendra",
     "add a trusted service to a clean, process-run premises", "\"Separate premises needed?\"",
     "Sehat ka bharosa aapse, paise ka bharosa bhi.", "Wahi graahak, naye kamaai ke raaste.",
     "Procedures aapki aadat hain. Growth Eko ki zimmedari."),
    ("O7", "Officer-grade ex-serviceman", "B", "veterans bodies, sainik welfare offices, cantonment towns",
     "a second career with command and respect", "\"Technology is not for me\"",
     "Desh ki seva ke baad, ilaake ki banking seva.", "Pension ke saath ek sammaanit business.",
     "Discipline aapki, har mahine growth Eko ki zimmedari."),
    ("O8", "Service agency owner", "B", "courier agency, telecom store, coaching or computer institute, insurance broker office",
     "more earning lines from the same staff and premises", "\"Dedicated hours?\"",
     "Aapke counter pe ab bank ka naam bhi.", "Staff aur jagah wahi, kamaai ke raaste zyada.",
     "Har mahine aage. Eko ka vaada."),
    ("O9", "Professional practice family", "C", "CA, tax consultant, accountant, financial advisor offices",
     "year-round footfall and trust", "\"Professional image?\"",
     "Log paisa aapke bharose rakhenge.", "ITR season ke baad bhi saal bhar ka kaam.",
     "Bharosa aapka, badhta business bhi aapka."),
]


def agent_section() -> str:
    """Everything above, told to a template agent writing a Banking Outlet template."""
    bullets = lambda items: "\n".join(f"- {i}" for i in items)
    personas = "\n".join(
        f"- {code} {name} (priority {prio}; found at {where}). Wants {want}. Holds back: {stop}. "
        f"Hooks: pride “{pride}” · earnings “{earn}” · growth “{grow}”"
        for code, name, prio, where, want, stop, pride, earn, grow in PERSONAS)
    faq = "\n".join(f"- {f['question']} → {f['pack_answer']['hinglish']}" for f in FAQ if "source" not in f)
    site = "\n".join(f"- {f['question']} → {f['answer']['hinglish']}" for f in SITE_FAQ)
    return f"""WHAT EKO SAYS ABOUT THE BANKING OUTLET (Eko's Creator Pack; the FAQ answers are confirmed by Eko — use them as facts, in the template's language):
{faq}

FROM EKO'S OWN SITE, kiosk.eko.in (facts too; the word rules below still apply to templates, so never “mini bank” or “mini branch”, and never a monthly earnings figure — the bot may quote the site's figures to someone who asks, a template may not):
{site}
- Eko delivers and sets up the devices (laptop, passbook printer, Micro-ATM, biometric scanner) and the kiosk branding, trains in Hindi, and the operator completes IIBF and DRA certification within 9 months. Women operators earn 10% more commission and have a coordinator to call. Eko: 17+ years, ranked among SBI's best Business Correspondents, 1,100+ CSPs in 160+ districts.
- Real operators on the site: Sunita Devi (Rajasthan) served 10,000+ customers and helped 200+ villagers open savings accounts; Sanjeev Kumar (Chandauli, Bihar) and Alamgeer Ansari (Kokilpatti) say their CSP works like a small branch for daily banking and made them financially independent.

THREE PILLARS — every template should carry pride, earnings and growth, and may close on Eko's promise: “{CLOSING_LINE}” (in the template's language, never with a number attached):
{bullets(f"{name}: {what}. e.g. {lines}" for name, what, lines in PILLARS)}

THE PATH EKO RUNS WITH THE OPERATOR (good material for “you are never alone” and growth messages):
{bullets(f"{stage} ({when}): {what}" for stage, when, what in GROWTH_PATH)}

WHO WE SPEAK TO — Banking Outlet operators come from established business families and are graduates; women entrepreneurs are a priority. Pick the persona that fits the businesses this template goes to, answer what holds them back, and adapt (not copy) a hook into the template's language:
{personas}

WORDS WE DO NOT USE: never call it a job, naukri, vacancy, bharti or joining (it is apna business); never promise a salary, fixed, guaranteed or “pakka” income; no “zero investment”, “limited seats” or “aaj hi payment”; the operator is a Kiosk Operator, not a bank employee or officer, and the outlet is not a mini bank or branch; always write Eko as “Eko”. Being honest about the investment of up to ₹5 lakh and “apply free” builds trust."""
