package org.b3yond.utils;

import com.ibm.wala.classLoader.IClass;
import com.ibm.wala.classLoader.IMethod;
import com.ibm.wala.core.tests.callGraph.CallGraphTestUtil;
import com.ibm.wala.core.util.config.AnalysisScopeReader;
import com.ibm.wala.core.util.io.FileProvider;
import com.ibm.wala.ipa.callgraph.AnalysisScope;
import com.ibm.wala.ipa.cha.ClassHierarchy;
import com.ibm.wala.ipa.cha.ClassHierarchyFactory;
import com.ibm.wala.types.ClassLoaderReference;
import java.util.ArrayList;
import java.util.List;
import java.io.File;
import java.util.jar.JarFile;

public class JavaBinLoader {
    private final ClassHierarchy cha;

    public JavaBinLoader(String filePath) throws Exception {
        File file = new File(filePath);
        if (!file.exists()) {
            throw new IllegalArgumentException("File does not exist: " + filePath);
        }
        this.cha = setupAnalysis(filePath);
    }

    private static ClassHierarchy setupAnalysis(String filePath) throws Exception {
        File file = new File(filePath);
        AnalysisScope scope = AnalysisScope.createJavaAnalysisScope();

        // Add Java runtime
        String javaHome = System.getProperty("java.home");
        String rtJar = javaHome + File.separator + "lib" + File.separator + "rt.jar";
        File rtJarFile = new File(rtJar);

        // For Java 9+, use the following path instead of rt.jar
        String jmods = javaHome + File.separator + "jmods" + File.separator + "java.base.jmod";
        File jmodsFile = new File(jmods);

        if (jmodsFile.exists()) {
            scope.addToScope(ClassLoaderReference.Primordial, new JarFile(jmodsFile));
        } else if (rtJarFile.exists()) {
            scope.addToScope(ClassLoaderReference.Primordial, new JarFile(rtJarFile));
        } else {
            throw new IllegalStateException("Cannot find Java runtime classes");
        }

        // Handle jar files loading based on input path type
        if (file.isDirectory()) {
            // If input is directory, load all jar files from it
            File[] jarFiles = file.listFiles((dir, name) -> name.toLowerCase().endsWith(".jar"));
            if (jarFiles != null) {
                for (File jarFile : jarFiles) {
                    // System.out.println("Adding jar file to scope: " + jarFile);
                    scope.addToScope(ClassLoaderReference.Application, new JarFile(jarFile));
                }
            }
            // For directories, we'll use the first jar file as the main analysis target
            if (jarFiles != null && jarFiles.length > 0) {
                scope.addToScope(ClassLoaderReference.Application, new JarFile(jarFiles[0]));
            }
        } else {
            // If input is a single file
            if (filePath.toLowerCase().endsWith(".jar")) {
                scope.addToScope(ClassLoaderReference.Application, new JarFile(file));
            } else if (filePath.toLowerCase().endsWith(".class")) {
                // Get target fuzzer class name without .class extension
                String targetFuzzerName = file.getName().substring(0, file.getName().lastIndexOf('.'));
                System.out.println("Analyzing single class file: " + targetFuzzerName);

                // Get parent directory to include all related class files in the same directory
                File parentDir = file.getParentFile();

                if (parentDir != null && parentDir.exists()) {
                    // Instead of using AnalysisScopeReader which will include all classes,
                    // we'll manually filter and add only non-Fuzzer classes + our target Fuzzer
                    System.out.println("Using directory for analysis with filtered fuzzer classes: "
                            + parentDir.getAbsolutePath());

                    // Create a custom exclusion filter for fuzzer classes except our target
                    File[] classFiles = parentDir.listFiles((dir, name) -> {
                        // Include if it's our target fuzzer
                        if (name.equals(file.getName())) {
                            return true;
                        }
                        // Include if it's not a fuzzer class (doesn't contain "Fuzzer" in name)
                        if (name.endsWith(".class") && !name.contains("Fuzzer")) {
                            return true;
                        }
                        // Exclude all other fuzzer classes
                        return false;
                    });

                    if (classFiles != null) {
                        // Create a temporary directory to hold only our filtered class files
                        File tempDir = new File(parentDir, "temp_analysis_" + System.currentTimeMillis());
                        tempDir.mkdir();
                        tempDir.deleteOnExit();

                        // Copy filtered class files to temp directory
                        for (File classFile : classFiles) {
                            try {
                                File destFile = new File(tempDir, classFile.getName());
                                java.nio.file.Files.copy(classFile.toPath(), destFile.toPath());
                                destFile.deleteOnExit();
                            } catch (Exception e) {
                                System.err.println("Error copying class file: " + e.getMessage());
                            }
                        }

                        // Use the temp directory for analysis
                        scope = AnalysisScopeReader.instance.makeJavaBinaryAnalysisScope(
                                tempDir.getAbsolutePath(),
                                new FileProvider().getFile(CallGraphTestUtil.REGRESSION_EXCLUSIONS));
                    } else {
                        // Fallback to just analyzing the single file
                        scope = AnalysisScopeReader.instance.makeJavaBinaryAnalysisScope(
                                filePath,
                                new FileProvider().getFile(CallGraphTestUtil.REGRESSION_EXCLUSIONS));
                    }
                } else {
                    scope = AnalysisScopeReader.instance.makeJavaBinaryAnalysisScope(
                            filePath,
                            new FileProvider().getFile(CallGraphTestUtil.REGRESSION_EXCLUSIONS));
                }
            } else {
                scope = AnalysisScopeReader.instance.makeJavaBinaryAnalysisScope(
                        filePath,
                        new FileProvider().getFile(CallGraphTestUtil.REGRESSION_EXCLUSIONS));
            }
        }

        return ClassHierarchyFactory.make(scope);
    }

    public String[] findFuzzerTestMethod() {
        for (IClass klass : cha) {
            if (klass.getClassLoader().getReference().equals(ClassLoaderReference.Application)) {
                for (IMethod method : klass.getDeclaredMethods()) {
                    System.out.println("[DEBUG] Method: " + method.getName());
                    if (method.getName().toString().contains("fuzzerTestOneInput")) {
                        return new String[] { klass.getName().toString(), method.getName().toString() };
                    }
                }
            }
        }
        return null;
    }

    public String[] findAllMethodsWithKeyword(String keyword) {
        List<String> matchingMethods = new ArrayList<>();
        for (IClass klass : cha) {
            if (klass.getClassLoader().getReference().equals(ClassLoaderReference.Application)) {
                for (IMethod method : klass.getDeclaredMethods()) {
                    if (method.getSignature().toString().startsWith(keyword + "(")) {
                        matchingMethods.add(method.getSignature());
                    }
                }
            }
        }
        return matchingMethods.toArray(new String[0]);
    }

    public String findFirstMethodWithKeyword(String keyword) {
        String[] methods = findAllMethodsWithKeyword(keyword);
        return methods.length > 0 ? methods[0] : null;
    }

    public String[] getAllClassNames() {
        List<String> classNames = new ArrayList<>();
        for (IClass klass : cha) {
            if (klass.getClassLoader().getReference().equals(ClassLoaderReference.Application)) {
                classNames.add(klass.getName().toString());
            }
        }
        return classNames.toArray(new String[0]);
    }
}
