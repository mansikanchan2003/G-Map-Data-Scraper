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
        "keys": ["penalty", "penality", "jurmana", "fine", "dand", "band rahe", "band ho", "जुर्माना", "पेनल्टी", "दंड", "દંડ", "પેનલ્ટી", "ਜੁਰਮਾਨਾ", "ਪੈਨਲਟੀ"],
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
        "keys": ["commission kab", "kab milega commission", "payment kab", "paisa kab", "kab aayega", "kab milta", "settlement",
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
        "keys": ["process", "prakriya", "steps", "kaise bane", "kaise shuru", "kaise start", "how to become", "how to start",
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
                 "aeps", "money transfer", "pmjdy", "pmsby", "pmjjby", "atal pension", "kaun kaun si sevayein",
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
FAQ = FAQ + SITE_FAQ

# Other ways people ask the same thing (2026-10-18: the team wants the bot to
# understand a question however it is put, not only in the FAQ's words). The
# spelling and the script do not need listing: "naukari", "नौकरी" and "ਨੌਕਰੀ"
# all match "naukri" by sound (see _sound). Only new words and phrasings go here.
MORE_KEYS: Dict[str, List[str]] = {
    "job": ["employee", "bank employee", "bank ka employee", "bank ka staff", "karmachari", "bank mein naukri",
            "bank me job", "permanent", "joining", "recruitment", "bharti", "sarkari naukri",
            "kya main bank ka", "bank wala ban", "मुलाजिम", "कर्मचारी", "નોકરિયાત", "ਮੁਲਾਜ਼ਮ"],
    "real": ["sach", "sacha", "sachcha", "bharosa", "vishwas", "trust", "scam", "dhokha", "thagi", "nakli", "legit",
             "authorized", "authorised", "registered company", "sahi company", "eko kya hai", "eko company", "eko kya company", "kaun si company", "company ka naam",
             "विश्वास", "नकली", "ठगी", "ભરોસો", "ਭਰੋਸਾ"],
    "fees": ["fees lagegi", "kitni fees", "form fees", "charge lagega", "registration fees", "apply free",
             "free hai", "mufat", "muft", "paise lagenge apply", "मुफ्त", "ફ્રી", "ਮੁਫ਼ਤ"],
    "investment": ["kitna lagana", "kitna lagega", "paise lagane", "paisa lagana", "lagana padega", "cost",
                   "budget", "capital", "amount lagega", "kitne rupaye", "kitna kharch", "5 lac", "पैसे लगाने",
                   "कितना लगेगा", "કેટલા પૈસા", "ਕਿੰਨੇ ਪੈਸੇ"],
    "devices": ["saman", "samaan", "equipment", "atm machine", "fingerprint", "thumb machine", "passbook machine",
                "kya kya milega", "setup", "सामान", "સામાન", "ਸਮਾਨ"],
    "with_shop": ["dukan", "shop", "kahan baithna", "jagah chahiye", "counter", "ghar se chala",
                  "ghar par chala", "kitne baje", "kitne ghante", "દુકાનમાં"],
    "training": ["sikhaenge", "sikhna", "seekhna", "pariksha", "test dena", "kaise sikhe",
                 "सीखना", "परीक्षा", "શીખવું", "ਸਿੱਖਣਾ"],
    "family": ["ghar wale", "gharwale", "beta chala", "wife chala", "koi aur chala", "relative", "rishtedar",
               "साथ में", "ઘરના", "ਘਰਵਾਲੇ"],
    "earnings": ["kitna kamaa", "kitna kama", "kitni kamai", "kitne paise milenge", "kitna paisa milega",
                 "fayda", "faida", "labh", "earn", "how much earn", "income kitni", "mahine ka kitna", "monthly kitna", "kitna banega",
                 "फायदा", "लाभ", "ફાયદો", "ਫ਼ਾਇਦਾ"],
    "salary": ["fix paisa", "fixed income", "har mahine fix", "pakka paisa", "guaranteed income", "guarantee income", "income guarantee", "garanti",
               "fix milega", "पक्का", "ગેરંટી", "ਪੱਕਾ"],
    "women": ["mahilaon", "ladki", "aurto", "auraton", "beti chala", "lady operator", "स्त्री", "ਔਰਤਾਂ"],
    # Not "chutti" or "holiday": "aaj chutti hai?" asks whether we are open, not about the penalty.
    "penalty": ["band rakha", "band kar diya", "lambe samay band", "kitne din band"],
    "eligibility": ["kaun ban sakta", "main ban sakta", "kya main apply", "kya mai apply", "can i apply",
                    "qualification", "padhai kitni", "kitna padha", "umar", "age limit", "yogya hun",
                    "उम्र", "आयु", "ઉંમર", "ਉਮਰ"],
    "cibil": ["credit report", "loan chal raha", "loan liya", "emi", "default", "credit history", "सिबिल स्कोर"],
    "documents": ["kya kya lagega", "kya lagega", "proof", "kagzat", "papers chahiye", "aadhar", "aadhaar", "pan card",
                  "police", "certificate chahiye", "कागजात", "આધાર", "ਆਧਾਰ"],
    "commission_paid": ["paisa kab aayega", "kab tak milega paisa", "payment date", "kis tareekh", "tarikh",
                        "account mein kab", "kab credit", "कब मिलेगा", "ક્યારે મળશે", "ਕਦੋਂ ਮਿਲੇਗਾ"],
    "process": ["aage kya karna", "aage kya", "next step", "shuru kaise", "kaise judein", "kaise jude", "kaise apply",
                "how to apply", "kitne din lagenge", "kitna time lagega", "kab tak shuru", "जुड़ना", "शुरू कैसे"],
    "services": ["kya kya kaam", "kya services", "kaun kaun se kaam", "account kholna", "cash withdrawal", "पैसे निकालना", "खाता खोलना"],
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


def _words(text: str) -> List[str]:
    # Indic vowel signs are not \w, so the Indic blocks are named whole: "ફોર્મ" is one word, not three.
    return re.findall(r"[\wऀ-෿₹]+", (text or "").lower())


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


def _where(key: str, words: List[str], sounds: List[str]) -> Optional[frozenset]:
    """The positions of the words a key matches in the message, or None if it does not."""
    parts = _words(key)
    if not parts:
        return None
    n = len(parts)
    for i in range(len(words) - n + 1):
        if all(_same(parts[j], words[i + j], sounds[i + j]) for j in range(n)):
            return frozenset(range(i, i + n))
    # An Indic key may carry a suffix in the message ("सेवा" in "सेवाएँ").
    if not _LATIN.search(key):
        for i in range(len(words) - n + 1):
            if all(parts[j] in words[i + j] for j in range(n)):
                return frozenset(range(i, i + n))
    return None


def match(text: str, limit: int = 2) -> List[str]:
    """
    The FAQ entries a message asks about, best first; empty when none fits.

    A key matches its words said in order, spelt or written in any script.
    The same words are counted once for an entry, so a question naming
    "commission" is not counted twice for the Hindi and the English key.
    """
    words = _words(text)
    sounds = [_sound(w) for w in words]
    scores: Dict[str, float] = {}
    for f in FAQ:
        hits = []
        for key in f["keys"]:
            at = _where(key, words, sounds)
            if at is not None:
                hits.append((1 + len(_norm(key).strip()) / 20, at))
        covered, score = set(), 0.0
        for weight, at in sorted(hits, key=lambda h: -h[0]):
            if not at <= covered:
                score += weight
                covered |= at
        if score:
            scores[f["id"]] = score
    ranked = sorted(scores, key=lambda i: -scores[i])
    # A second answer only when it is about as strong as the first.
    if len(ranked) > 1 and scores[ranked[1]] < scores[ranked[0]] * 0.6:
        ranked = ranked[:1]
    return ranked[:limit]


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
    faq = "\n".join(f"- {f['question']} → {f['answer']['hinglish']}" for f in FAQ)
    return f"""WHAT EKO SAYS ABOUT THE BANKING OUTLET (Eko's Creator Pack; the FAQ answers are confirmed by Eko — use them as facts, in the template's language):
{faq}

THREE PILLARS — every template should carry pride, earnings and growth, and may close on Eko's promise: “{CLOSING_LINE}” (in the template's language, never with a number attached):
{bullets(f"{name}: {what}. e.g. {lines}" for name, what, lines in PILLARS)}

THE PATH EKO RUNS WITH THE OPERATOR (good material for “you are never alone” and growth messages):
{bullets(f"{stage} ({when}): {what}" for stage, when, what in GROWTH_PATH)}

WHO WE SPEAK TO — Banking Outlet operators come from established business families and are graduates; women entrepreneurs are a priority. Pick the persona that fits the businesses this template goes to, answer what holds them back, and adapt (not copy) a hook into the template's language:
{personas}

WORDS WE DO NOT USE: never call it a job, naukri, vacancy, bharti or joining (it is apna business); never promise a salary, fixed, guaranteed or “pakka” income; no “zero investment”, “limited seats” or “aaj hi payment”; the operator is a Kiosk Operator, not a bank employee or officer, and the outlet is not a mini bank or branch; always write Eko as “Eko”. Being honest about the investment of up to ₹5 lakh and “apply free” builds trust."""
