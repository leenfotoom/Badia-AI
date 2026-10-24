# رفع BADIA AI على GitHub (نسخة جاهزة)

## قبل الرفع
- اختاري **Private** أولاً، وراجعي تراخيص البيانات والملفات قبل تغييره إلى Public.
- **لا ترفعي** ملف BADIA_AI_MVP.zip الأصلي، ولا مجلدات `.venv` أو `node_modules`.
- الملف `BADIA_AI_GitHub_Ready.zip` هو نسخة مصدر نظيفة. **فكّي الضغط** قبل الرفع؛ لا ترفعي ZIP نفسه كملف وحيد.
- إذا أنشأتِ مستودع GitHub يحتوي README ابتدائيًا، لا تنفذي push مباشرة من دون دمج التاريخ. الأفضل أن يكون المستودع فارغًا.

## رفع باستخدام GitHub Desktop (أسهل بدون أوامر)
1. فكّي ضغط ملف BADIA_AI_GitHub_Ready.zip في جهازك.
2. افتحي GitHub Desktop وسجلي دخولك.
3. اختاري File > Add local repository، وحددي مجلد BADIA-AI.
4. إذا ظهر أنه ليس مستودع Git، اختاري Create a repository here.
5. اكتبي Initial commit: BADIA AI واحفظي الـCommit.
6. إذا لم تنشئي المستودع على GitHub، اضغطي Publish repository واختاري Private.
7. لو المستودع موجود مسبقًا على GitHub، اربطيه بالـremote المناسب بدل نشر مستودع ثانٍ.

## بديل PowerShell (مستودع جديد فارغ موجود على GitHub)
من داخل المجلد BADIA-AI بعد فك الضغط:

```powershell
git init
git branch -M main
git add .
git commit -m "Initial commit: BADIA AI"
git remote add origin https://github.com/USERNAME/BADIA-AI.git
git push -u origin main
```

استبدلي USERNAME باسم حسابك (وهذا يفترض أنك سجلت الدخول إلى GitHub وأن المستودع فارغ).

## ماذا بقي بعد الرفع؟
- تأكدي من عرض README.md، مجلد `frontend/`, `backend/`, `models/`, `data/`.
- ارفعي صورًا للشاشات لاحقًا داخل README إن رغبتِ.
- لا تسردي توقعات 7 أكتوبر 2026 كأنها تنبؤات مباشرة بتاريخ اليوم.
