package org.b3yond.utils;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.type.Type;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.visitor.VoidVisitorAdapter;

import java.io.FileInputStream;

public class JVMSignatureGenerator {
    public static void generateSignatures(String sourceFilePath) {
        try {
            // Parse the Java file
            FileInputStream in = new FileInputStream(sourceFilePath);
            JavaParser parser = new JavaParser();
            CompilationUnit cu = parser.parse(in).getResult().orElseThrow();

            // Get package name
            String packageName = cu.getPackageDeclaration()
                    .map(pd -> pd.getName().asString())
                    .orElse("");

            // Visit all methods
            cu.accept(new MethodVisitor(packageName), null);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static class MethodVisitor extends VoidVisitorAdapter<Void> {
        private final String packageName;

        public MethodVisitor(String packageName) {
            this.packageName = packageName;
        }

        @Override
        @SuppressWarnings("unchecked")
        public void visit(MethodDeclaration method, Void arg) {
            // Get class name from the parent node
            String className = method.findAncestor(com.github.javaparser.ast.body.ClassOrInterfaceDeclaration.class)
                    .map(c -> c.getNameAsString())
                    .orElse("");

            // Build JVM signature
            String signature = buildJVMSignature(method, className);

            // Print the original method and its JVM signature
            System.out.println("Source: " + method.getDeclarationAsString(false, false, false));
            System.out.println("JVM Signature: " + signature);
            System.out.println();
        }

        private String buildJVMSignature(MethodDeclaration method, String className) {
            StringBuilder sb = new StringBuilder();

            // Add class name (with package if available)
            if (!packageName.isEmpty()) {
                sb.append(packageName.replace('.', '/'))
                        .append("/");
            }
            sb.append(className)
                    .append(".")
                    .append(method.getNameAsString());

            // Add parameters
            sb.append("(");
            for (Parameter param : method.getParameters()) {
                appendJVMType(sb, param.getType());
            }
            sb.append(")");

            // Add return type
            appendJVMType(sb, method.getType());

            return sb.toString();
        }

        private void appendJVMType(StringBuilder sb, Type type) {
            String typeStr = type.asString();

            // Handle arrays
            int arrayCount = (int) typeStr.chars().filter(ch -> ch == '[').count();
            typeStr = typeStr.replace("[]", "");

            // For array types, prepend '[' for each dimension
            for (int i = 0; i < arrayCount; i++) {
                sb.append('[');
            }

            // For primitive types, if it's an array we need special handling
            boolean isPrimitive = isPrimitiveType(typeStr);
            if (arrayCount > 0 && isPrimitive) {
                appendPrimitiveType(sb, typeStr);
            } else if (isPrimitive) {
                // Regular primitive type
                appendPrimitiveType(sb, typeStr);
            } else {
                // Reference type - add L prefix if not an array, always add ; suffix
                if (arrayCount == 0) {
                    sb.append('L');
                }
                sb.append(typeStr.replace('.', '/'));
                if (!typeStr.endsWith(";")) {
                    sb.append(';');
                }
            }
        }

        private boolean isPrimitiveType(String typeStr) {
            return typeStr.equals("byte") || typeStr.equals("char") ||
                    typeStr.equals("double") || typeStr.equals("float") ||
                    typeStr.equals("int") || typeStr.equals("long") ||
                    typeStr.equals("short") || typeStr.equals("boolean") ||
                    typeStr.equals("void");
        }

        private void appendPrimitiveType(StringBuilder sb, String typeStr) {
            switch (typeStr) {
                case "byte":
                    sb.append('B');
                    break;
                case "char":
                    sb.append('C');
                    break;
                case "double":
                    sb.append('D');
                    break;
                case "float":
                    sb.append('F');
                    break;
                case "int":
                    sb.append('I');
                    break;
                case "long":
                    sb.append('J');
                    break;
                case "short":
                    sb.append('S');
                    break;
                case "boolean":
                    sb.append('Z');
                    break;
                case "void":
                    sb.append('V');
                    break;
            }
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.out.println("Usage: JVMSignatureGenerator <source-file-path>");
            return;
        }

        generateSignatures(args[0]);
    }
}
