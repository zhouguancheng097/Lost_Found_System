package cn.campus.lostfound;

import static cn.campus.lostfound.Support.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import javax.imageio.ImageIO;
import jakarta.servlet.http.*;
import org.springframework.core.io.*;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.*;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.*;

@Controller
public class Api {
    private final Business business; private final Db db; private final Search search;
    private final Map<String,List<Long>> attempts=new ConcurrentHashMap<>();
    public Api(Business business,Db db,Search search){this.business=business;this.db=db;this.search=search;}
    @GetMapping("/") public ResponseEntity<Resource> index(){return ResponseEntity.ok().contentType(MediaType.TEXT_HTML).body(new ClassPathResource("static/index.html"));}
    @ModelAttribute public void guard(HttpServletRequest request,HttpServletResponse response) {
        response.setHeader("X-Content-Type-Options","nosniff");response.setHeader("X-Frame-Options","DENY");response.setHeader("Referrer-Policy","same-origin");
        response.setHeader("Content-Security-Policy","default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'");
        response.setHeader("Cache-Control","no-store");
        if(!Set.of("GET","HEAD","OPTIONS").contains(request.getMethod())) {
            HttpSession session=request.getSession(false);
            if(session==null)throw fail(401,"登录态过期，请重新登录后再操作");
            if(!sameToken((String)session.getAttribute("csrf"),request.getHeader("X-CSRF-Token")))throw fail(403,"页面验证已失效，请刷新后重试");
        }
    }
    private Map<String,Object> user(HttpServletRequest request,boolean required) {
        HttpSession session=request.getSession(false);Object uid=session==null?null:session.getAttribute("uid");
        if(uid==null){if(required)throw fail(401,"请先登录");return null;}
        Map<String,Object> current=business.active(((Number)uid).longValue());
        Object version=session.getAttribute("session_version");
        if ((version instanceof Number number?number.longValue():0)!=id(current,"session_version")) throw fail(401,"登录信息已变更，请重新登录");
        return current;
    }
    private Map<String,Object> admin(HttpServletRequest request){Map<String,Object> user=user(request,true);business.requireAdmin(user);return user;}
    @GetMapping("/api/session") @ResponseBody public Map<String,Object> session(HttpServletRequest request) {
        HttpSession session=request.getSession(true);if(session.getAttribute("csrf")==null)session.setAttribute("csrf",token());
        Map<String,Object> user=null;
        try{user=user(request,false);}catch(Support.AppException exception){session.removeAttribute("uid");session.removeAttribute("session_version");}
        return data("user",user==null?null:business.safeUser(user),"csrf",session.getAttribute("csrf"),"categories",CATEGORIES);
    }
    private void limit(HttpServletRequest request) {
        long now=System.currentTimeMillis();if(attempts.size()>5000)attempts.clear();
        List<Long> history=attempts.computeIfAbsent(request.getRemoteAddr(),ignored->new ArrayList<>());
        synchronized(history){history.removeIf(time->time<now-60000);if(history.size()>=12)throw fail(429,"尝试次数过多，请一分钟后再试");history.add(now);}
    }
    @PostMapping("/api/register") @ResponseBody public Object register(@RequestBody Map<String,Object> input,HttpServletRequest request){limit(request);return business.register(input);}
    @PostMapping("/api/login") @ResponseBody public Object login(@RequestBody Map<String,Object> input,HttpServletRequest request){limit(request);Map<String,Object> user=business.login(input);request.changeSessionId();HttpSession session=request.getSession();session.setAttribute("uid",id(user,"id"));session.setAttribute("session_version",id(user,"session_version"));session.setAttribute("csrf",token());return data("user",business.safeUser(user),"csrf",session.getAttribute("csrf"));}
    @PostMapping("/api/logout") @ResponseBody public Object logout(HttpServletRequest request){request.getSession().invalidate();return data("ok",true);}
    @GetMapping("/api/account/profile") @ResponseBody public Object profile(HttpServletRequest request){return business.safeUser(user(request,true));}
    @PutMapping("/api/account/profile") @ResponseBody public Object updateProfile(@RequestBody Map<String,Object> input,HttpServletRequest request){Map<String,Object> current=user(request,true);limit(request);return business.updateProfile(current,input);}
    @PostMapping("/api/account/password") @ResponseBody public Object changePassword(@RequestBody Map<String,Object> input,HttpServletRequest request){Map<String,Object> current=user(request,true);limit(request);business.changePassword(current,input);request.getSession().invalidate();return data("ok",true);}
    @DeleteMapping("/api/account") @ResponseBody public Object deleteAccount(@RequestBody Map<String,Object> input,HttpServletRequest request){business.deleteAccount(user(request,true),text(input,"password",1,128));request.getSession().invalidate();return data("ok",true);}
    @GetMapping("/api/items") @ResponseBody public Object items(@RequestParam Map<String,String> filters){return search.search(filters);}
    @GetMapping("/api/items/{id}") @ResponseBody public Object detail(@PathVariable long id,HttpServletRequest request){return business.detail(id,user(request,false));}
    @PostMapping("/api/items") @ResponseBody public Object create(@RequestBody Map<String,Object> input,HttpServletRequest request){return business.createItem(user(request,true),input);}
    @PutMapping("/api/items/{id}") @ResponseBody public Object edit(@PathVariable long id,@RequestBody Map<String,Object> input,HttpServletRequest request){return business.editItem(user(request,true),id,input);}
    @DeleteMapping("/api/items/{id}") @ResponseBody public Object delete(@PathVariable long id,HttpServletRequest request){business.deleteItem(user(request,true),id);return data("ok",true);}
    @PostMapping("/api/items/{id}/close") @ResponseBody public Object close(@PathVariable long id,HttpServletRequest request){business.close(user(request,true),id,false);return data("ok",true);}
    @PostMapping("/api/items/{id}/resolve") @ResponseBody public Object resolve(@PathVariable long id,HttpServletRequest request){business.close(user(request,true),id,true);return data("ok",true);}
    @GetMapping("/api/items/{id}/matches") @ResponseBody public Object matches(@PathVariable long id,HttpServletRequest request){Map<String,Object> user=user(request,true),item=business.requireItem(id);business.requireOwner(user,item);if(!"OPEN".equals(item.get("status")))throw fail(409,"仅审核通过且未结束的信息可以查看推荐");return search.matches(item);}
    @GetMapping("/api/mine/items") @ResponseBody public Object mine(HttpServletRequest request){List<Map<String,Object>> items=db.ownItems(id(user(request,true),"id"));items.forEach(item->item.put("images",db.images(id(item,"id"))));return items;}
    @PostMapping("/api/items/{id}/claims") @ResponseBody public Object apply(@PathVariable long id,@RequestBody Map<String,Object> input,HttpServletRequest request){return business.apply(user(request,true),id,input);}
    @GetMapping("/api/mine/claims") @ResponseBody public Object myClaims(HttpServletRequest request){long uid=id(user(request,true),"id");return db.claims().stream().filter(claim->id(claim,"applicant_id")==uid).toList();}
    @PostMapping("/api/claims/{id}/withdraw") @ResponseBody public Object withdraw(@PathVariable long id,HttpServletRequest request){business.withdraw(user(request,true),id);return data("ok",true);}
    @GetMapping("/api/notifications") @ResponseBody public Object notifications(HttpServletRequest request){return db.notifications(id(user(request,true),"id"));}
    @PostMapping("/api/notifications/read") @ResponseBody public Object read(HttpServletRequest request){db.readNotifications(id(user(request,true),"id"));return data("ok",true);}
    @GetMapping("/api/admin/{section}") @ResponseBody public Object adminList(@PathVariable String section,HttpServletRequest request){admin(request);return switch(section){case "items"->db.allItems();case "claims"->db.claims();case "users"->db.users();case "logs"->db.logs();default->throw fail(404,"管理页面不存在");};}
    @PostMapping("/api/admin/items/{id}/review") @ResponseBody public Object review(@PathVariable long id,@RequestBody Map<String,Object> input,HttpServletRequest request){business.review(admin(request),id,Boolean.TRUE.equals(input.get("approve")),text(input,"reason",0,300));return data("ok",true);}
    @PostMapping("/api/admin/claims/{id}/{action}") @ResponseBody public Object claimAction(@PathVariable long id,@PathVariable String action,@RequestBody Map<String,Object> input,HttpServletRequest request){business.claimAction(admin(request),id,action,text(input,"reason",0,300));return data("ok",true);}
    @PostMapping("/api/admin/users/{id}/{action}") @ResponseBody public Object accountAction(@PathVariable long id,@PathVariable String action,@RequestBody Map<String,Object> input,HttpServletRequest request){business.accountAction(admin(request),id,action,text(input,"reason",1,300));return data("ok",true);}
    @GetMapping("/api/health") @ResponseBody public Object health(){return data("ok",true,"ai",search.healthy());}
    @PostMapping("/api/uploads") @ResponseBody public Object upload(@RequestParam("file") MultipartFile file,@RequestParam(name="kind",defaultValue="PUBLIC") String kind,HttpServletRequest request) throws Exception {
        Map<String,Object> user=user(request,true);if(!Set.of("PUBLIC","PROOF").contains(kind))throw fail(400,"附件类型错误");
        if(file.isEmpty()||file.getSize()>5242880)throw fail(400,"图片不能为空且不能超过 5MB");byte[] bytes=file.getBytes();
        String mime;String extension;
        if(bytes.length>=8&&bytes[0]==(byte)0x89&&bytes[1]=='P'&&bytes[2]=='N'&&bytes[3]=='G'){mime="image/png";extension="png";}
        else if(bytes.length>=3&&bytes[0]==(byte)0xff&&bytes[1]==(byte)0xd8&&bytes[2]==(byte)0xff){mime="image/jpeg";extension="jpg";}
        else if(bytes.length>=12&&new String(bytes,0,4,java.nio.charset.StandardCharsets.US_ASCII).equals("RIFF")&&new String(bytes,8,4,java.nio.charset.StandardCharsets.US_ASCII).equals("WEBP")){throw fail(400,"当前版本请使用 JPEG 或 PNG 图片");}
        else throw fail(400,"仅允许真实的 JPEG、PNG 图片");
        try(var stream=ImageIO.createImageInputStream(new ByteArrayInputStream(bytes))) {
            var readers=ImageIO.getImageReaders(stream);if(!readers.hasNext())throw fail(400,"图片内容损坏");var reader=readers.next();
            try{reader.setInput(stream);if((long)reader.getWidth(0)*reader.getHeight(0)>20000000)throw fail(400,"图片分辨率过高");if(reader.read(0)==null)throw fail(400,"图片内容损坏");}finally{reader.dispose();}
        }catch(Support.AppException exception){throw exception;}catch(Exception exception){throw fail(400,"无法识别图片内容");}
        String name=UUID.randomUUID()+"."+extension;Path directory=AppConfig.dataDir().resolve(kind.equals("PUBLIC")?"uploads":"proofs");Files.createDirectories(directory);Path destination=directory.resolve(name);Files.write(destination,bytes);
        Map<String,Object> attachment=data("owner_id",user.get("id"),"stored_name",name,"mime",mime,"kind",kind,"created_at",now());
        try{db.insertAttachment(attachment);}catch(RuntimeException exception){Files.deleteIfExists(destination);throw exception;}return data("id",attachment.get("id"));
    }
    @GetMapping("/media/{id}") public ResponseEntity<Resource> media(@PathVariable long id,HttpServletRequest request) {
        Map<String,Object> attachment=db.attachment(id);if(attachment==null)throw fail(404,"图片不存在");Map<String,Object> user=user(request,false);
        boolean allowed=user!=null&&(business.admin(user)||id(user,"id")==id(attachment,"owner_id"));
        if(!allowed&&"PUBLIC".equals(attachment.get("kind"))){Long itemId=db.imageItem(id);if(itemId!=null){Map<String,Object> item=db.item(itemId);allowed=item!=null&&business.visible(item,user);}}
        if(!allowed)throw fail(403,"无权查看此附件");
        Path file=AppConfig.dataDir().resolve("PUBLIC".equals(attachment.get("kind"))?"uploads":"proofs").resolve(str(attachment,"stored_name"));
        if(!Files.isRegularFile(file))throw fail(404,"图片文件不存在");return ResponseEntity.ok().contentType(MediaType.parseMediaType(str(attachment,"mime"))).body(new FileSystemResource(file));
    }
    @ExceptionHandler(Support.AppException.class) @ResponseBody public ResponseEntity<?> error(Support.AppException exception){return ResponseEntity.status(exception.status).body(data("error",exception.getMessage()));}
    @ExceptionHandler(DataIntegrityViolationException.class) @ResponseBody public ResponseEntity<?> integrity(){return ResponseEntity.status(409).body(data("error","用户名已存在、申请重复或已有领取人，请刷新核对"));}
    @ExceptionHandler(DataAccessException.class) @ResponseBody public ResponseEntity<?> database(){return ResponseEntity.status(409).body(data("error","数据正在更新，请稍后刷新重试"));}
    @ExceptionHandler(MaxUploadSizeExceededException.class) @ResponseBody public ResponseEntity<?> uploadSize(){return ResponseEntity.status(413).body(data("error","图片不能超过 5MB"));}
    @ExceptionHandler({org.springframework.http.converter.HttpMessageNotReadableException.class,org.springframework.web.method.annotation.MethodArgumentTypeMismatchException.class,org.springframework.web.bind.MissingServletRequestParameterException.class,org.springframework.web.multipart.support.MissingServletRequestPartException.class}) @ResponseBody public ResponseEntity<?> invalid(){return ResponseEntity.badRequest().body(data("error","请求参数格式不正确或缺少必填字段"));}
    @ExceptionHandler(Exception.class) @ResponseBody public ResponseEntity<?> unexpected(Exception exception){System.err.println("Request failed: "+exception.getClass().getSimpleName());return ResponseEntity.internalServerError().body(data("error","操作未完成，请稍后重试"));}
}
