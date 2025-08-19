package org.b3yond;

/*
 * Copyright (c) 2002 - 2006 IBM Corporation.
 * All rights reserved. This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License v1.0
 * which accompanies this distribution, and is available at
 * http://www.eclipse.org/legal/epl-v10.html
 *
 * Contributors:
 *     IBM Corporation - initial API and implementation
 *     42-b3yond-6ug - extended to support customized slicing
 */
import com.ibm.wala.classLoader.IClass;
import com.ibm.wala.classLoader.IMethod;
import com.ibm.wala.classLoader.JarFileModule;
import com.ibm.wala.core.tests.callGraph.CallGraphTestUtil;
import com.ibm.wala.core.util.config.AnalysisScopeReader;
import com.ibm.wala.core.util.io.FileProvider;
import com.ibm.wala.ipa.callgraph.AnalysisCacheImpl;
import com.ibm.wala.ipa.callgraph.AnalysisOptions;
import com.ibm.wala.ipa.callgraph.AnalysisScope;
import com.ibm.wala.ipa.callgraph.CGNode;
import com.ibm.wala.ipa.callgraph.CallGraph;
import com.ibm.wala.ipa.callgraph.Entrypoint;
import com.ibm.wala.ipa.callgraph.impl.Util;
import com.ibm.wala.ipa.callgraph.impl.DefaultEntrypoint;
import com.ibm.wala.ipa.callgraph.propagation.InstanceKey;
import com.ibm.wala.ipa.callgraph.propagation.PointerAnalysis;
import com.ibm.wala.ipa.callgraph.IAnalysisCacheView;
import com.ibm.wala.ipa.callgraph.propagation.SSAPropagationCallGraphBuilder;
import com.ibm.wala.ipa.cha.ClassHierarchy;
import com.ibm.wala.ipa.cha.ClassHierarchyFactory;
import com.ibm.wala.ipa.slicer.Slicer;
import com.ibm.wala.ipa.slicer.Slicer.ControlDependenceOptions;
import com.ibm.wala.ipa.slicer.Slicer.DataDependenceOptions;
import com.ibm.wala.ipa.slicer.Statement;
import com.ibm.wala.ipa.slicer.MethodEntryStatement;
import com.ibm.wala.types.TypeReference;
import com.ibm.wala.types.ClassLoaderReference;
import com.ibm.wala.types.TypeName;
import com.ibm.wala.util.CancelException;
import com.ibm.wala.util.WalaException;
import com.ibm.wala.util.debug.UnimplementedError;
import com.ibm.wala.util.io.CommandLine;
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.Collection;
import java.util.Properties;
import java.util.Collections;
import java.util.jar.JarFile;
import java.util.List;
import java.util.HashSet;
import java.util.Set;

/**
 * This simple example WALA application computes a slice (see {@link Slicer})
 * and fires off the PDF
 * viewer to view a dot-ted representation of the slice.
 *
 * <p>
 * This is an example program on how to use the slicer.
 *
 * <p>
 * See the 'PDFSlice' launcher included in the 'launchers' directory.
 *
 * @see Slicer
 * @author sfink
 */
public class AIXCCJavaSlice {

    /**
     * Validate that the command-line arguments obey the expected usage.
     *
     * @throws UnsupportedOperationException if command-line is malformed.
     */
    static void validateCommandLine(Properties p) {
        if (p.get("appClass") == null) {
            throw new UnsupportedOperationException("expected command-line to include -appClass");
        }
        if (p.get("jarPath") == null) {
            throw new UnsupportedOperationException("expected command-line to include -jarPath");
        }
        if (p.get("mainClass") == null) {
            throw new UnsupportedOperationException("expected command-line to include -mainClass");
        }

        if (p.get("mainMethod") == null) {
            throw new UnsupportedOperationException("expected command-line to include -mainMethod");
        }

        if (p.get("targetMethodFile") == null) {
            throw new UnsupportedOperationException("expected command-line to include -targetMethodFile");
        }

        if (p.get("outputFile") == null) {
            throw new UnsupportedOperationException("expected command-line to include -outputFile");
        }
    }

    private static boolean isApplicationClass(CGNode node) {
        return node.getMethod().getDeclaringClass().getClassLoader().getReference()
                .equals(ClassLoaderReference.Application);
    }

    /**
     * Usage: PDFSlice -appClass [class file name] -jarPath [jar files folder]
     * -mainClass [entry point class] -mainMethod [entry point method] -targetClass
     * [target class name] -targetMethodFile [file containing the list of target
     * methods] -outputFile [file to save the results]
     * 
     * @see com.ibm.wala.ipa.slicer.Slicer.DataDependenceOptions
     */
    public static void main(String[] args)
            throws IllegalArgumentException, CancelException, IOException {
        run(args);
    }

    /** see {@link #main(String[])} for command-line arguments */
    public static void run(String[] args)
            throws IllegalArgumentException, CancelException, IOException {
        // parse the command-line into a Properties object
        Properties p = CommandLine.parse(args);
        // validate that the command-line has the expected format
        validateCommandLine(p);

        // run the applications
        run(
                p.getProperty("appClass"),
                p.getProperty("jarPath"),
                p.getProperty("mainClass"),
                p.getProperty("mainMethod"),
                p.getProperty("targetMethodFile"),
                p.getProperty("outputFile"));
    }

    private static CGNode findMethodNode(CallGraph cg, String methodSignature) {
        for (CGNode n : cg) {
            if (n.getMethod().getSignature().equals(methodSignature)) {
                return n;
            }
        }
        System.out.println("Warning: cannot find this method on the call graph: " + methodSignature);

        return null;
    }

    /** Get the slice result for one method */
    private static Collection<Statement> sliceOneMethod(SSAPropagationCallGraphBuilder builder, CallGraph cg,
            String targetMethod) {

        CGNode targetNode = findMethodNode(cg, targetMethod);

        // cannot find the method on the call graph
        if (targetNode == null) {
            return null;
        }

        System.out.println("Info: target function node on call graph found: " + targetNode.getMethod().getSignature());

        MethodEntryStatement firstStatement = new MethodEntryStatement(targetNode);

        System.out.println("Info: entry statement of the target function found: " + firstStatement.toString());

        final PointerAnalysis<InstanceKey> pointerAnalysis = builder.getPointerAnalysis();

        Collection<Statement> slice = null;

        try {
            slice = Slicer.computeBackwardSlice(firstStatement, cg, pointerAnalysis, DataDependenceOptions.NO_BASE_NO_HEAP_NO_EXCEPTIONS,
                    ControlDependenceOptions.FULL);
        } catch (CancelException e) {
            System.err.println("Error: cannot get slice for " + targetMethod);
            e.printStackTrace();
        }

        System.out.println("Info: slicing for target function done: " + targetMethod);
        return slice;
    }

    private static void writeSliceOneMethod(String targetMethod, String outputFile, Collection<Statement> slice) {

        Set<String> set = new HashSet<>();

        // get the signatures of unique application methods in the slice
        for (Statement stmt : slice) {
            if (isApplicationClass(stmt.getNode())) {
                set.add(stmt.getNode().getMethod().getSignature());
            }
        }

        String result = targetMethod + "," + String.join(",", set);

        System.out.println("Info: saving slice results of " + targetMethod + " into " + outputFile);
        try {
            Files.write(Paths.get(outputFile),
                    (result + System.lineSeparator()).getBytes(),
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    /** Backward Slicing for target methods */
    // DataDependenceOptions.NONE
    // ControlDependenceOptions.FULL
    private static boolean backwardMethodSlicing(SSAPropagationCallGraphBuilder builder, CallGraph cg,
            String targetMethodFile, String outputFile) {

        System.out.println("Info: start slicing process");

        try {
            List<String> methods = Files.readAllLines(Paths.get(targetMethodFile));
			System.out.println("Info: target functions for slicing " + methods);
            for (String method : methods) {
                Collection<Statement> slice = sliceOneMethod(builder, cg, method);
                if (slice != null) {
                    writeSliceOneMethod(method, outputFile, slice);
                }
            }
        } catch (IOException e) {
            e.printStackTrace();
        }
        return true;
    }

    /** Set up options for analysis */
    private static AnalysisOptions setupAnalysisOptions(Entrypoint entrypoint) {
        // Set up the analysis options
        AnalysisOptions options = new AnalysisOptions();
        // set up entry point as desired by user
        options.setEntrypoints(Collections.singletonList(entrypoint));
        // enable full reflection analysis
        options.setReflectionOptions(AnalysisOptions.ReflectionOptions.ONE_FLOW_TO_CASTS_APPLICATION_GET_METHOD);

        return options;
    }

    /** Create an Entrypoint based on the given main class and main method */
    private static Entrypoint findEntryPoint(String mainClassName, String mainMethodName, ClassHierarchy cha) {

        // try to find the main class
        TypeReference mainClassRef = TypeReference.find(
                ClassLoaderReference.Application,
                TypeName.string2TypeName(mainClassName));

        IClass mainClassObj = cha.lookupClass(mainClassRef);

        // main class not found
        if (mainClassObj == null) {
            System.err.println("Error: cannot find main class");
            System.exit(1);
        } else {
            System.out.println("Info: main class found " + mainClassObj.getName().toString());
        }

        // Find the main method
        IMethod mainMethodObj = null;
        for (IMethod method : mainClassObj.getDeclaredMethods()) {
            if (method.getName().toString().equals(mainMethodName)) { // Your target method
                mainMethodObj = method;
                break;
            }
        }

        // main class not found
        if (mainMethodObj == null) {
            System.err.println("Error: cannot find main method");
            System.exit(1);
        } else {
            System.out.println("Info: main method found " + mainMethodObj.getSignature());
        }

        return new DefaultEntrypoint(mainMethodObj, cha);
    }

    /** Establish the analysis scope to include the app and the jars */
    private static AnalysisScope buildAnalysisScope(String appClass, String jarPath) {

        AnalysisScope scope = null;

        // add target app into analysis scope
        try {
            // CallGraphTestUtil.REGRESSION_EXCLUSIONS defaults to
            // "Java60RegressionExclusions.txt" under $PWD
            scope = AnalysisScopeReader.instance.makeJavaBinaryAnalysisScope(
                    appClass, new FileProvider().getFile(CallGraphTestUtil.REGRESSION_EXCLUSIONS));
        } catch (IOException e) {
            System.err.println("Error: cannot init an analysis scope from the entry class(es): " + appClass);
            e.printStackTrace();
        }

        System.out.println("Info: added entry class(es) to analysis scope from " + appClass);

        // include the jar files into the analysis scope
        File folder = new File(jarPath);
        File[] jarFiles = folder.listFiles((dir, name) -> name.toLowerCase().endsWith(".jar"));

        if (jarFiles == null || jarFiles.length == 0) {
            System.out.println("Warning: no .jar files found");
        } else {
            // Add each JAR file to the analysis scope
            for (File jarFile : jarFiles) {
                try {
                    scope.addToScope(ClassLoaderReference.Application, new JarFileModule(new JarFile(jarFile)));
                    System.out.println("Info: added JAR to analysis scope: " + jarFile.getName());
                } catch (IOException e) {
                    System.err.println("Error: cannot add JAR file into the analysis scope: " + jarFile.getName());
                    e.printStackTrace();
                }
            }
        }

        return scope;

    }

    /**
     * Function to run backward slicing on a given set of methods, assuming the
     * entry class and entry method are both provided
     * 
     * @param appClass
     * @param jarPath
     * @param mainClass
     * @param mainMethod
     * @param targetMethodFile
     * @param outputFile
     * @return a Process running the PDF viewer to visualize the dot'ted
     *         representation of the slice
     */
    public static void run(
            String appClass,
            String jarPath,
            String mainClass,
            String mainMethod,
            String targetMethodFile,
            String outputFile)
            throws IllegalArgumentException, CancelException, IOException {
        try {
            // create an analysis scope representing the appClass as a J2SE application
            AnalysisScope scope = buildAnalysisScope(appClass, jarPath);

            // build a class hierarchy, call graph, and system dependence graph
            ClassHierarchy cha = ClassHierarchyFactory.make(scope);

            // Construct the entry point
            Entrypoint entrypoint = findEntryPoint(mainClass, mainMethod, cha);

            // Set up the analysis options
            AnalysisOptions options = setupAnalysisOptions(entrypoint);

            IAnalysisCacheView cache = new AnalysisCacheImpl();

            // Run 1-CFA analysis
            SSAPropagationCallGraphBuilder builder = Util.makeNObjBuilder(
                    1,
                    options,
                    cache,
                    cha);

            // Build the the call graph
            CallGraph cg = builder.makeCallGraph(options, null);

            System.out.println("Info: call graph builder completed");

            backwardMethodSlicing(builder, cg, targetMethodFile, outputFile);

        } catch (UnimplementedError | WalaException e) {
            e.printStackTrace();
        }
    }
}
