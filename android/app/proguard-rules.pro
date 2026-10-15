# OMEGA-X Ascension - minimal R8/ProGuard keep rules.
# Debug builds are unaffected; these rules only apply to release builds.
# Keep Android entry points referenced from AndroidManifest.xml.
-keep public class * extends android.app.Activity
-keep public class * extends android.app.Application
-keepattributes SourceFile,LineNumberTable
