package cn.campus.lostfound;

import java.nio.file.*;
import javax.sql.DataSource;
import org.sqlite.SQLiteConfig;
import org.sqlite.SQLiteDataSource;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.context.annotation.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.web.servlet.config.annotation.*;
import org.springframework.web.multipart.support.StandardServletMultipartResolver;

@Configuration
@ComponentScan("cn.campus.lostfound")
@MapperScan(basePackages="cn.campus.lostfound",annotationClass=org.apache.ibatis.annotations.Mapper.class)
@EnableWebMvc
@EnableTransactionManagement
public class AppConfig implements WebMvcConfigurer {
    public static Path dataDir() { return Path.of(System.getProperty("app.data", "data")).toAbsolutePath(); }
    @Bean public DataSource dataSource() throws Exception {
        Files.createDirectories(dataDir());
        SQLiteConfig config = new SQLiteConfig(); config.enforceForeignKeys(true); config.setBusyTimeout(5000);
        SQLiteDataSource source = new SQLiteDataSource(config);
        source.setUrl("jdbc:sqlite:" + dataDir().resolve("lostfound.db"));
        new ResourceDatabasePopulator(new ClassPathResource("schema.sql")).execute(source);
        return source;
    }
    @Bean public SqlSessionFactoryBean sqlSessionFactory(DataSource source) {
        SqlSessionFactoryBean factory = new SqlSessionFactoryBean(); factory.setDataSource(source); return factory;
    }
    @Bean public DataSourceTransactionManager transactionManager(DataSource source) { return new DataSourceTransactionManager(source); }
    @Bean public StandardServletMultipartResolver multipartResolver() { return new StandardServletMultipartResolver(); }
    @Override public void addResourceHandlers(ResourceHandlerRegistry registry) { registry.addResourceHandler("/assets/**").addResourceLocations("classpath:/static/"); }
}
