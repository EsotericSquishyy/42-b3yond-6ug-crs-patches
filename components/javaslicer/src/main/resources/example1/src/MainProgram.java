public class MainProgram {
    public static void printWithBorder(String text) {
        String border = "*".repeat(text.length() + 4);
        System.out.println(border);
        System.out.println("* " + text + " *");
        System.out.println(border);
    }

    public static void main(String[] args) {
        String text = "Hello World";
        
        // Using methods from StringUtils in the JAR
        System.out.println("Original: " + text);
        System.out.println("Reversed: " + StringUtils.reverseString(text));
        System.out.println("Uppercase: " + StringUtils.toUpperCase(text));
        System.out.println("Lowercase: " + StringUtils.toLowerCase(text));

        // Calling our new function
        printWithBorder("Testing Border");
    }
}
