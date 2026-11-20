package cn.campus.lostfound;

import java.nio.file.*;
import jakarta.servlet.MultipartConfigElement;
import org.apache.catalina.Context;
import org.apache.catalina.Wrapper;
import org.apache.catalina.startup.Tomcat;
import org.apache.tomcat.util.http.Rfc6265CookieProcessor;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.servlet.DispatcherServlet;

public final class Server {
    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(System.getProperty("app.port", "8080"));
        Path runtime = Path.of("runtime").toAbsolutePath(); Files.createDirectories(runtime.resolve("web"));
        Tomcat tomcat = new Tomcat(); tomcat.setBaseDir(runtime.resolve("tomcat").toString()); tomcat.setPort(port);
        tomcat.getConnector().setProperty("address", "127.0.0.1");
        tomcat.getConnector().setMaxPostSize(6 * 1024 * 1024);
        Context context = tomcat.addContext("", runtime.resolve("web").toString());
        Rfc6265CookieProcessor cookies = new Rfc6265CookieProcessor(); cookies.setSameSiteCookies("lax"); context.setCookieProcessor(cookies);
        context.setUseHttpOnly(true); context.setSessionTimeout(30);
        AnnotationConfigWebApplicationContext spring = new AnnotationConfigWebApplicationContext(); spring.register(AppConfig.class);
        Wrapper servlet = Tomcat.addServlet(context,"mvc",new DispatcherServlet(spring));
        servlet.setLoadOnStartup(1); servlet.setMultipartConfigElement(new MultipartConfigElement(runtime.toString(),5242880,6291456,0));
        context.addServletMappingDecoded("/","mvc");
        Runtime.getRuntime().addShutdownHook(new Thread(() -> { try { tomcat.stop(); tomcat.destroy(); } catch (Exception ignored) {} }));
        tomcat.start();
        System.out.println("Lost & Found ready: http://127.0.0.1:" + port);
        tomcat.getServer().await();
    }
}
