package org.b3yond.utils;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.file.Path;
import java.nio.file.Files;
import java.io.IOException;

public class JVMSignatureGeneratorTest {

    private final ByteArrayOutputStream outContent = new ByteArrayOutputStream();
    // private final PrintStream originalOut = System.out;

    @BeforeEach
    void setUpStreams() {
        System.setOut(new PrintStream(outContent));
    }

    @Test
    void testSimpleMethod(@TempDir Path tempDir) throws IOException {
        String code = """
                package test;
                public class Simple {
                    public int add(int a, int b) {
                        return a + b;
                    }
                }
                """;
        Path sourceFile = createTempFile(tempDir, "Simple.java", code);

        JVMSignatureGenerator.generateSignatures(sourceFile.toString());

        String output = outContent.toString();
        assertTrue(output.contains("test/Simple.add(II)I"));
    }

    @Test
    void testArrayMethod(@TempDir Path tempDir) throws IOException {
        String code = """
                package test;
                public class ArrayTest {
                    public int[] processArray(String[][] input) {
                        return null;
                    }
                }
                """;
        Path sourceFile = createTempFile(tempDir, "ArrayTest.java", code);

        JVMSignatureGenerator.generateSignatures(sourceFile.toString());

        String output = outContent.toString();
        assertTrue(output.contains("test/ArrayTest.processArray("));
    }

    @Test
    void testObjectMethod(@TempDir Path tempDir) throws IOException {
        String code = """
                package test;
                import java.util.List;
                public class ObjectTest {
                    public List<String> process(Object obj) {
                        return null;
                    }
                }
                """;
        Path sourceFile = createTempFile(tempDir, "ObjectTest.java", code);

        JVMSignatureGenerator.generateSignatures(sourceFile.toString());

        String output = outContent.toString();
        System.out.println(output);
        assertTrue(output.contains("test/ObjectTest.process(LObject;"));
    }

    @Test
    void testVoidMethod(@TempDir Path tempDir) throws IOException {
        String code = """
                package test;
                public class VoidTest {
                    public void doNothing() {
                    }
                }
                """;
        Path sourceFile = createTempFile(tempDir, "VoidTest.java", code);

        JVMSignatureGenerator.generateSignatures(sourceFile.toString());

        String output = outContent.toString();
        assertTrue(output.contains("test/VoidTest.doNothing()V"));
    }

    private Path createTempFile(Path dir, String fileName, String content) throws IOException {
        Path file = dir.resolve(fileName);
        Files.writeString(file, content);
        return file;
    }

    @Test
    void testMainMethodWithInvalidArgs() {
        JVMSignatureGenerator.main(new String[] {});
        assertTrue(outContent.toString().contains("Usage:"));
    }
}
