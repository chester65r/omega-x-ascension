# خيارات API للنماذج المجانية — Omega X Ascension

**تاريخ المراجعة:** 11 أكتوبر 2026. **النطاق:** عشرة مزوّدين رئيسيين للاستدلال المستضاف عبر API، وليس كل موقع أو مزوّد موجود. لم تُرسل أي طلبات استدلال أثناء هذه المراجعة، ولم يُنشأ حساب أو مفتاح أو تُشترَ أرصدة.

> **تنبيه:** أوزان النماذج المفتوحة التي يمكن تنزيلها مجاناً ليست API مستضافاً مجانياً. تشغيلها ذاتياً يحتاج حاسوباً وموارد مناسبة؛ والاستضافة لدى طرف ثالث قد تكون مدفوعة.

## الخلاصة

الأوضح كخدمة مستضافة بلا تكلفة حالياً: **Google Gemini، OpenRouter، Groq، Cloudflare Workers AI، وMistral Free mode**—مع حصص أو إتاحة متغيرة. **NVIDIA NIM** يوفّر نقاط نهاية مجانية للتجربة والتقييم فقط بشروط محدودة، وليس مجانياً للإنتاج. **Together AI** لا يوفّر استدلالاً عاماً مجانياً، **GitHub Models متوقف**، وضع **SambaNova** المجاني غير محسوم بسبب تعارض صفحاتها الرسمية، و**Hugging Face Inference Providers** لا يمنح مستخدم Free رصيداً مضمنًا حسب جدول الأسعار المفصل.

## المقارنة

| المنصة | الحالة الحالية | نماذج/حصة مجانية موثقة | حدود مهمة وطريقة الربط |
|---|---|---|---|
| **Google Gemini API / AI Studio** | متاح ضمن Free Tier | نماذج معروضة بسعر إدخال/إخراج صفري تشمل `gemini-3.8-flash` و`gemini-3.6-flash` و`gemini-3.8-live`. الإتاحة تتغير حسب النموذج والمنطقة. | حصة محدودة بمعدلات RPM وTPM وRPD لكل مشروع/نموذج؛ الأرقام الفعلية تُعرض في AI Studio ولا يوجد حد عام موحد منشور. التجديد اليومي عند منتصف الليل بتوقيت المحيط الهادئ. أساس متوافق مع OpenAI (Beta): `https://generativelanguage.googleapis.com/v1beta/openai/`. لا يوجد اشتراط وسيلة دفع موثق للوصول المجاني؛ الترقية المدفوعة تحتاج بيانات دفع وقد تتطلب 5 دولارات مقدماً. السعودية مدرجة ضمن المناطق المدعومة في التحقق السابق للمشروع؛ يجب إعادة التحقق من أهلية الحساب والمنطقة عند الاستخدام. |
| **OpenRouter** | متاح عبر نماذج/موجّه مجاني متغير | الموجّه `openrouter/free` ومثال كتالوجي `apodex/apodex-1.1-mini:free`. قد يظهر نموذج بسعر صفري دون لاحقة `:free`، لكن ذلك لا يضمن استمراره ضمن مسارات free. | واجهة OpenAI-compatible: `https://openrouter.ai/api/v1`. التوافر يتغير وقد يظهر 429 عند حدود المزوّد أو 402 عند رصيد سلبي. شراء 10 دولارات أرصدة يرفع طبقة الحد اليومي؛ لم توثق الصفحات شرط شراء للوصول الأساسي المجاني. لا تعتمد على معرّف ثابت دون فحص الكتالوج الحي. |
| **GroqCloud** | خطة Free موثقة | لم تثبت الصفحات الرسمية المفحوصة معرّف نموذج محدداً على أنه مشمول مجاناً؛ قائمة النماذج/الأسعار لا تثبت أهلية كل نموذج لخطة Free. | OpenAI-compatible: `https://api.groq.com/openai/v1`. الخطة المجانية لها حدود منفصلة، لكن الأرقام الدقيقة لحساب Free غير متاحة في الصفحات العامة المفحوصة؛ راجع لوحة Limits. اشتراط وسيلة دفع لاستخدام Free غير محسوم، وترقية Developer تتطلب وسيلة دفع. |
| **Cloudflare Workers AI** | متاح بمخصص مجاني يومي | **10,000 Neurons يومياً لكل حساب** ضمن Workers Free/Paid. أمثلة كتالوجية تشمل `@cf/meta/llama-3.1-8b-instruct` و`@cf/openai/gpt-oss-20b`؛ الوثائق لا تضمن أن كل نموذج من الأمثلة مؤهل للحصة المجانية. | تتجدد الحصة عند 00:00 UTC؛ بعد استهلاكها قد تتوقف الطلبات ما لم ينطبق وصول مدفوع. حجم الاستخدام الممكن يعتمد على كلفة Neurons لكل نموذج. REST وواجهة متوافقة مع OpenAI، ومنها `/v1/chat/completions`. لا توثق الصفحة شرط بطاقة للحصة المجانية؛ خطة Workers المدفوعة لها حد أدنى 5 دولارات شهرياً. |
| **Mistral La Plateforme / Studio** | Free mode متاح افتراضياً للحسابات الجديدة | الاستخدام الشهري والحدود المجانية موثقان، لكن المصادر الرسمية المفحوصة لا تحدد أي model IDs مشمولة. لذلك لا نعتبر `mistral-small-latest` أو `mistral-large-latest` مجانيين دون التحقق في الحساب. | `https://api.mistral.ai/v1/chat/completions` بصيغة OpenAI-like، لكن لم يُعثر على ضمان drop-in كامل. صفحة التفعيل تقول لا تحتاج بطاقة لتمكين Free mode؛ دليل أول طلب يذكر 402 عند غياب وسيلة دفع، وحدّ الانتقال إلى الاستخدام المدفوع غير واضح. |
| **Together AI** | ليس لديه وصول عام مجاني للاستدلال | لا توجد خطة عامة مجانية حسب وثائق الفوترة؛ لا تخلط بين أوزان مجانية أو تطبيق Together Chat وبين API مدفوع. | الحد الأدنى لشراء الرصيد **5 دولارات**، ويجب وجود رصيد موجب قبل الاستدعاء. OpenAI-compatible: `https://api.together.ai/v1`. الحدود متغيرة حسب النموذج. |
| **SambaNova Cloud** | غير محسوم بسبب تعارض رسمي | وثيقة الحدود تسمي Free Tier عند عدم ربط وسيلة دفع لكنها لا تذكر حصة؛ صفحة الخطط تقول إن Free تتطلب إضافة وسيلة دفع وشراء أرصدة قبل أول طلب. لا يمكن تأكيد API مجاني حالي. رصيد 5 دولارات القديم كان عرضاً منتهياً بعد 3 أشهر. | OpenAI-compatible: `https://api.sambanova.ai/v1`، مع مسارات Responses وAnthropic Messages. حصة 20 مليون رمز يومياً المنشورة تخص Developer ولا تثبت حصة Free. |
| **NVIDIA NIM API Catalog** | مجاني للتقييم فقط | الكتالوج يعرض نقاط نهاية “Free Endpoint”، ومن أمثلتها `kimi-k3` و`nemotron-3-ultra-550b-a55b` و`nemotron-3.5-lightning-30b-a3b`. الشروط تصفها كتجربة/تقييم محدود، لا استضافة إنتاجية مجانية؛ لم يُنشر رقم حصة أو مدة موحدة. | يحتاج عضوية NVIDIA Developer ومفتاح API. يدعم NIM مسارات OpenAI-like مثل `/v1/chat/completions`؛ يؤخذ عنوان الاستضافة وتعليمات كل نموذج من صفحة الكتالوج، لا من عنوان المثال المحلي. لا يوجد اشتراط بطاقة موثق لبدء الوصول التجريبي. شروط التجربة تمنع الاستخدام الإنتاجي وتحظر إرسال محتوى سري أو حساس أو بيانات دفع/صحة. |
| **GitHub Models** | **متوقف** | تقاعدت الخدمة بالكامل في **30 يوليو 2026**؛ لم يعد Playground أو الكتالوج أو Inference API أو BYOK متاحاً. | المسارات القديمة، ومنها `/inference/chat/completions`، تاريخية وغير صالحة للتكامل الحالي. |
| **Hugging Face Inference Providers** | الخدمة موجودة لكن Free بلا رصيد مضمن | جدول الأسعار المفصل يقول إن Free لديه **0 رصيد شهري** ويلزمه شراء أرصدة أو الترقية. عبارة “free tier” العامة في صفحة النظرة العامة تتعارض مع الجدول التفصيلي؛ اعتمدنا جدول التسعير المحدد. أسماء مثل `openai/gpt-oss-120b` أمثلة كتالوج وليست دليلاً على المجانية. | OpenAI-compatible: `https://router.huggingface.co/v1` مع رمز Inference Providers. استخدام مفتاح خارجي ينقل الفوترة للمزوّد الخارجي؛ لا يجعل التوجيه نفسه مجانياً. |

## التوصيات للتطبيق

1. ابدأ عند السماح بربط مزوّد آخر بـ **Gemini أو Cloudflare Workers AI** بعد التحقق من الحساب والمنطقة والنموذج والحصة الفعلية.
2. استخدم **OpenRouter** للتجارب وتعدد الخيارات؛ افحص المزوّد النهائي وسياسة البيانات لكل طلب، ولا تفترض استمرار أي نموذج مجاني.
3. تعامل مع **Groq وMistral** كبدائل مشروطة بعد مراجعة لوحة الحساب والفوترة؛ لم تثبت المصادر معرّفات نماذج مجانية محددة لهما.
4. اجعل **NVIDIA NIM** للتقييم فقط. لا تبنِ تشغيل الإنتاج على نقطة نهاية تجريبية.
5. لا تعتمد على Together أو GitHub Models أو رصيد Hugging Face المجاني كمصدر API بلا تكلفة. أبقِ SambaNova غير مؤكدة حتى تُحل مفارقة الخطة رسمياً.
6. لا تعرض في التطبيق مزوداً أو نموذجاً كخيار قابل للاستخدام ما لم يكن مفتاحه محفوظاً بأمان على الخادم، والنموذج مثبتاً في قائمة سماح، واختُبرت معالجة 402/429 والحدود. لا تحوّل الطلب بصمت إلى خدمة مدفوعة.
7. اعرض إشعار خصوصية قبل إرسال المحتوى؛ Google Free قد يستخدم المدخلات والمخرجات لتحسين الخدمات وقد يراجعها بشر، وOpenRouter يمرر المحتوى إلى مزوّد خلفي، وشروط تجربة NVIDIA تمنع إرسال بيانات حساسة.

## الحالة الحالية في Omega X Ascension

- الإعداد الموجود للمشروع ما زال يستخدم مفتاح Google AI Studio المملوك للمستخدم في **Vercel Preview فقط**، والنموذج المحدد `gemini-3.8-flash`؛ لم يُضف المفتاح إلى التطبيق أو APK ولم يُضف متغير Production.
- تمت مراجعة أن السعودية مدرجة في مناطق Gemini المدعومة، وقُبلت سابقاً شروط بيانات Google Free Tier، وأكد المستخدم أن Cloud Billing غير مربوط. الحصص خاصة بالمشروع والنموذج، وليست غير محدودة.
- استُهلك سابقاً طلب دردشة حي واحد مصرح به وأعاد `GEMINI_OK`؛ لم يُرسل أي طلب نموذج إضافي في هذه الجولة، ولم يُنشأ حساب أو مفتاح لأي مزوّد جديد.
- تعذر تحديث Preview في هذه الجلسة لعدم توفر أداة نشر Vercel. لذلك لا يُقال إن موفّراً جديداً رُبط أو أن الخادم المنشور قد تحدّث.

## المصادر الرسمية

### Gemini
[التسعير](https://ai.google.dev/gemini-api/docs/pricing) · [حدود الاستخدام](https://ai.google.dev/gemini-api/docs/rate-limits) · [الفوترة](https://ai.google.dev/gemini-api/docs/billing) · [الشروط](https://ai.google.dev/gemini-api/terms) · [توافق OpenAI](https://ai.google.dev/gemini-api/docs/openai) · [النماذج](https://ai.google.dev/gemini-api/docs/models) · [المناطق](https://ai.google.dev/gemini-api/docs/available-regions)

### OpenRouter
[الموجّه المجاني](https://openrouter.ai/docs/guides/routing/routers/free-router) · [النماذج المجانية](https://openrouter.ai/docs/guides/routing/model-variants/free) · [الحدود](https://openrouter.ai/docs/api_reference/limits) · [الكتالوج](https://openrouter.ai/docs/guides/overview/models) · [خصوصية المزوّدين](https://openrouter.ai/docs/guides/privacy/provider-logging) · [ZDR](https://openrouter.ai/docs/guides/features/zdr) · [الخصوصية](https://openrouter.ai/privacy) · [واجهة النماذج](https://openrouter.ai/api/v1/models)

### GroqCloud
[الحدود](https://console.groq.com/docs/rate-limits) · [النماذج](https://console.groq.com/docs/models) · [الفوترة](https://console.groq.com/docs/billing-faqs) · [البيانات](https://console.groq.com/docs/your-data) · [اتفاقية الخدمة](https://console.groq.com/docs/legal/services-agreement) · [البدء](https://console.groq.com/docs/quickstart)

### Cloudflare Workers AI
[التسعير](https://developers.cloudflare.com/workers-ai/platform/pricing/) · [الحدود](https://developers.cloudflare.com/workers-ai/platform/limits/) · [استخدام البيانات](https://developers.cloudflare.com/workers-ai/platform/data-usage/) · [REST API](https://developers.cloudflare.com/workers-ai/get-started/rest-api/) · [توافق OpenAI](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)

### Mistral
[حدود الاستخدام](https://docs.mistral.ai/admin/billing-usage/usage-limits) · [تفعيل Free](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key) · [أول طلب](https://docs.mistral.ai/getting-started/quickstarts/developer/first-api-request) · [المحادثات](https://docs.mistral.ai/api/endpoint/chat) · [الأسعار](https://mistral.ai/pricing) · [الشروط التجارية](https://legal.mistral.ai/terms/commercial-terms-of-service/) · [ZDR](https://docs.mistral.ai/admin/monitor-comply/zero-data-retention)

### Together AI
[الفوترة](https://docs.together.ai/docs/billing) · [حدود الاستخدام](https://docs.together.ai/docs/billing-usage-limits) · [المفاتيح](https://docs.together.ai/docs/api-keys-authentication) · [توافق OpenAI](https://docs.together.ai/docs/inference/openai-compatibility) · [النماذج](https://docs.together.ai/docs/serverless/models) · [الشروط](https://www.together.ai/terms-of-service) · [الخصوصية](https://www.together.ai/privacy)

### SambaNova
[الحدود](https://docs.sambanova.ai/docs/en/models/rate-limits) · [النماذج](https://docs.sambanova.ai/docs/en/models/sambacloud-models) · [المفاتيح والعناوين](https://docs.sambanova.ai/docs/en/get-started/api-keys-urls) · [الخطط](https://cloud.sambanova.ai/plans/pricing) · [توافق OpenAI](https://docs.sambanova.ai/docs/en/features/openai-compatibility) · [خصوصية المنتج](https://sambanova.ai/products/sambacloud)

### NVIDIA NIM
[الكتالوج](https://build.nvidia.com/models) · [الاكتشاف](https://build.nvidia.com/explore/discover) · [الأسئلة الشائعة](https://forums.developer.nvidia.com/t/nvidia-nim-faq/300317) · [شروط التجربة](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf) · [مرجع API](https://docs.nvidia.com/nim/large-language-models/latest/api-reference.html)

### GitHub Models
[إشعار التقاعد](https://docs.github.com/en/github-models) · [الإعلان التاريخي](https://github.blog/changelog/2025-05-15-github-models-api-now-available/) · [توثيق API التاريخي](https://docs.github.com/en/rest/models/inference)

### Hugging Face
[التسعير](https://huggingface.co/docs/inference-providers/pricing) · [نظرة عامة](https://huggingface.co/docs/inference-providers/index) · [الأمان](https://huggingface.co/docs/inference-providers/security) · [المحادثات](https://huggingface.co/docs/inference-providers/tasks/chat-completion) · [توليد النص](https://huggingface.co/docs/inference-providers/tasks/text-generation)

> الأسعار والسياسات والكتالوجات قابلة للتغيير. أعد التحقق من الصفحات الرسمية ولوحة الحساب قبل الإطلاق وبصفة دورية. هذه المقارنة لا تعني أن أي مزوّد إضافي أُضيف إلى التطبيق.
