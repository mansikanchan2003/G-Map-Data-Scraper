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
            "hinglish": "INR 5 lakh aur usse upar, location aur setup par nirbhar.",
            "en": "₹5 lakh and above, depending on the location and the setup.",
            "hi": "₹5 लाख और उससे ऊपर, लोकेशन और सेटअप पर निर्भर।",
            "gu": "₹5 લાખ અને તેથી વધુ, સ્થાન અને સેટઅપ પર આધારિત.",
            "pa": "₹5 ਲੱਖ ਅਤੇ ਉਸ ਤੋਂ ਵੱਧ, ਲੋਕੇਸ਼ਨ ਅਤੇ ਸੈੱਟਅੱਪ 'ਤੇ ਨਿਰਭਰ।",
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
        "keys": ["salary", "selery", "fixed salary", "tankhwah", "tankha", "vetan", "pagar", "mahina fix", "fixed", "सैलरी", "वेतन", "तनख्वाह", "પગાર", "ਤਨਖਾਹ"],
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

# Some words belong to more than one question ("fixed salary" names the
# salary question, not the job one); the longer, more specific key wins.
_BY_ID = {f["id"]: f for f in FAQ}
_LATIN = re.compile(r"[A-Za-z]")


def _norm(text: str) -> str:
    return " " + re.sub(r"[^\wऀ-෿₹]+", " ", (text or "").lower()) + " "


def match(text: str, limit: int = 2) -> List[str]:
    """The FAQ entries a message asks about, best first; empty when none fits."""
    norm = _norm(text)
    scores: Dict[str, float] = {}
    for f in FAQ:
        score = 0.0
        for key in f["keys"]:
            k = _norm(key).strip()
            if not k:
                continue
            # Latin words must match whole words ("fd" not inside "fdi");
            # Indic words may carry suffixes, so a substring is enough.
            hit = f" {k} " in norm if _LATIN.search(k) else k in norm
            if hit:
                score += 1 + len(k) / 20
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

WORDS WE DO NOT USE: never call it a job, naukri, vacancy, bharti or joining (it is apna business); never promise a salary, fixed, guaranteed or “pakka” income; no “zero investment”, “limited seats” or “aaj hi payment”; the operator is a Kiosk Operator, not a bank employee or officer, and the outlet is not a mini bank or branch; always write Eko as “Eko”. Being honest about the ₹5 lakh+ investment and “apply free” builds trust."""
