public class StringUtils {
    public static String reverseString(String input) {
        return new StringBuilder(input).reverse().toString();
    }
    
    public static String toUpperCase(String input) {
        return reverseString(input);
    }
    
    public static String toLowerCase(String input) {
        return toUpperCase(input);
    }
}
