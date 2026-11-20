package cn.campus.lostfound;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.*;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class Support {
    public static final List<String> CATEGORIES = List.of("证件卡片", "数码电子", "钥匙", "包袋", "衣物配饰", "水杯餐具", "雨伞", "书籍文具", "其他");
    private static final SecureRandom RANDOM = new SecureRandom();
    private Support() {}
    public static Map<String, Object> data(Object... pairs) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int index = 0; index < pairs.length; index += 2) result.put(pairs[index].toString(), pairs[index + 1]);
        return result;
    }
    public static String str(Map<String, ?> value, String key) { return Objects.toString(value.get(key), "").trim(); }
    public static long id(Map<String, ?> value, String key) {
        Object number = value.get(key);
        if (number instanceof Number numeric) return numeric.longValue();
        try { return Long.parseLong(Objects.toString(number, "0")); }
        catch (NumberFormatException exception) { throw fail(400, "编号格式不正确"); }
    }
    public static String text(Map<String, ?> value, String key, int min, int max) {
        String result = str(value, key);
        if (result.length() < min || result.length() > max) throw fail(400, key + " 长度须为 " + min + "～" + max + " 个字符");
        return result;
    }
    public static String now() { return Instant.now().toString(); }
    public static String token() {
        byte[] bytes = new byte[24]; RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }
    public static String hash(String password) {
        byte[] salt = new byte[16]; RANDOM.nextBytes(salt);
        return "210000:" + Base64.getEncoder().encodeToString(salt) + ":" + Base64.getEncoder().encodeToString(derive(password, salt, 210000));
    }
    private static byte[] derive(String password, byte[] salt, int rounds) {
        PBEKeySpec spec = new PBEKeySpec(password.toCharArray(), salt, rounds, 256);
        try { return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded(); }
        catch (Exception exception) { throw new IllegalStateException(exception); }
        finally { spec.clearPassword(); }
    }
    public static boolean verify(String password, String stored) {
        try {
            String[] parts = stored.split(":");
            return MessageDigest.isEqual(derive(password, Base64.getDecoder().decode(parts[1]), Integer.parseInt(parts[0])), Base64.getDecoder().decode(parts[2]));
        } catch (RuntimeException exception) { return false; }
    }
    public static boolean sameToken(String first, String second) {
        return first != null && second != null && MessageDigest.isEqual(first.getBytes(StandardCharsets.UTF_8), second.getBytes(StandardCharsets.UTF_8));
    }
    public static AppException fail(int status, String message) { return new AppException(status, message); }
    public static class AppException extends RuntimeException {
        public final int status;
        public AppException(int status, String message) { super(message); this.status = status; }
    }
}
