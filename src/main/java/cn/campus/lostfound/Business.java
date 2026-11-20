package cn.campus.lostfound;

import static cn.campus.lostfound.Support.*;
import java.nio.file.*;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class Business {
    private final Db db;
    public Business(Db db) { this.db = db; }
    @jakarta.annotation.PostConstruct
    public void initialize() throws Exception {
        if (db.userByName("admin") == null) {
            String password = System.getenv("LOSTFOUND_ADMIN_PASSWORD");
            if (password == null || password.length() < 6) password = "123456";
            Map<String,Object> admin = data("username","admin","display_name","系统管理员","password_hash",hash(password),"role","ADMIN","created_at",now());
            db.insertUser(admin);
            Files.writeString(AppConfig.dataDir().resolve("admin-credentials.txt"),"用户名：admin\n密码：" + password + "\n首次初始化密码；在个人信息页修改密码后，请使用修改后的密码。升级不会自动恢复默认密码。\n");
        }
    }
    public Map<String,Object> active(long userId) {
        Map<String,Object> user = db.user(userId);
        if (user == null || !"ACTIVE".equals(user.get("status"))) throw fail(403,"账号已封禁或注销，请联系管理员");
        return user;
    }
    public boolean admin(Map<String,Object> user) { return user != null && "ADMIN".equals(user.get("role")); }
    public void requireAdmin(Map<String,Object> user) { if (!admin(user)) throw fail(403,"此操作需要管理员权限"); }
    public Map<String,Object> safeUser(Map<String,Object> user) {
        return data("id",user.get("id"),"username",user.get("username"),"display_name",user.get("display_name"),"role",user.get("role"),"phone",str(user,"phone"),"default_address",str(user,"default_address"));
    }
    @Transactional public Map<String,Object> register(Map<String,Object> input) {
        String username = text(input,"username",3,30);
        if (!username.matches("[A-Za-z0-9_]{3,30}")) throw fail(400,"用户名仅允许字母、数字和下划线");
        String password = text(input,"password",8,128);
        Map<String,Object> user = data("username",username.toLowerCase(Locale.ROOT),"display_name",text(input,"display_name",1,30),"password_hash",hash(password),"role","USER","created_at",now());
        db.insertUser(user); return safeUser(db.user(id(user,"id")));
    }
    public Map<String,Object> login(Map<String,Object> input) {
        Map<String,Object> user = db.userByName(text(input,"username",3,30).toLowerCase(Locale.ROOT));
        String password = text(input,"password",1,128);
        if (user == null || !verify(password,str(user,"password_hash"))) throw fail(401,"用户名或密码不正确");
        return active(id(user,"id"));
    }
    @Transactional public Map<String,Object> updateProfile(Map<String,Object> user,Map<String,Object> input) {
        Map<String,Object> current = active(id(user,"id"));
        String username = text(input,"username",3,30).toLowerCase(Locale.ROOT);
        if (!username.matches("[a-z0-9_]{3,30}")) throw fail(400,"登录账号仅允许 3～30 位字母、数字和下划线");
        if (!username.equals(current.get("username"))) {
            if (admin(current)) throw fail(400,"管理员登录账号固定为 admin");
            if (!verify(text(input,"current_password",1,128),str(current,"password_hash"))) throw fail(400,"当前密码不正确");
            Map<String,Object> existing = db.userByName(username);
            if (existing != null && id(existing,"id") != id(current,"id")) throw fail(409,"该登录账号已被使用");
        }
        String phone = text(input,"phone",0,25);
        if (!phone.isEmpty() && (!phone.matches("\\+?[0-9 ()-]{5,25}") || phone.replaceAll("[^0-9]","").length()<5)) throw fail(400,"电话号码格式不正确，可留空或填写含区号的电话号码");
        Map<String,Object> values = data("id",current.get("id"),"username",username,"display_name",text(input,"display_name",1,30),"phone",phone,"default_address",text(input,"default_address",0,100),"expected_hash",current.get("password_hash"));
        if (db.updateProfile(values)!=1) throw fail(409,"账号信息已变化，请刷新后重试");
        audit(current,"修改个人信息","user",id(current,"id"),"");
        return safeUser(db.user(id(current,"id")));
    }
    @Transactional public void changePassword(Map<String,Object> user,Map<String,Object> input) {
        Map<String,Object> current = active(id(user,"id"));
        if (!verify(text(input,"current_password",1,128),str(current,"password_hash"))) throw fail(400,"当前密码不正确");
        String password = text(input,"new_password",8,128);
        if (!password.equals(text(input,"confirm_password",8,128))) throw fail(400,"两次输入的新密码不一致");
        if (verify(password,str(current,"password_hash"))) throw fail(400,"新密码不能与当前密码相同");
        if (db.changePassword(id(current,"id"),str(current,"password_hash"),hash(password))!=1) throw fail(409,"密码已变化，请重新登录");
        audit(current,"修改密码","user",id(current,"id"),"");
    }
    public Map<String,Object> requireItem(long itemId) {
        Map<String,Object> item = db.item(itemId); if (item == null) throw fail(404,"信息不存在或已删除"); return item;
    }
    public void requireOwner(Map<String,Object> user,Map<String,Object> item) {
        if (!admin(user) && id(user,"id") != id(item,"owner_id")) throw fail(403,"只能管理自己发布的信息");
    }
    public boolean visible(Map<String,Object> item,Map<String,Object> user) {
        if (user != null && (admin(user) || id(user,"id") == id(item,"owner_id"))) return true;
        Map<String,Object> owner = db.user(id(item,"owner_id"));
        return owner != null && "ACTIVE".equals(owner.get("status")) && Set.of("OPEN","HANDOVER","CLAIMED","RESOLVED","CLOSED").contains(str(item,"status"));
    }
    public Map<String,Object> detail(long itemId,Map<String,Object> user) {
        Map<String,Object> item = requireItem(itemId);
        if (!visible(item,user)) throw fail(404,"信息不存在或尚未公开");
        boolean own = user != null && (admin(user) || id(user,"id") == id(item,"owner_id"));
        if (!own) { item.remove("hidden_features"); item.remove("review_note"); }
        if (!own && (user == null || db.contactAllowed(itemId,id(user,"id")) == 0)) item.remove("contact");
        item.put("images",db.images(itemId)); item.put("claim_count",db.claimCount(itemId));
        item.put("owner_name",db.user(id(item,"owner_id")).get("display_name")); return item;
    }
    private Map<String,Object> itemInput(Map<String,Object> input) {
        String type = str(input,"type"); if (!Set.of("LOST","FOUND").contains(type)) throw fail(400,"请选择寻物或招领");
        String category = str(input,"category"); if (!CATEGORIES.contains(category)) throw fail(400,"物品类别不正确");
        String date = str(input,"event_date");
        try { if (LocalDate.parse(date).isAfter(LocalDate.now(ZoneId.of("Asia/Shanghai")))) throw fail(400,"事件日期不能晚于今天"); }
        catch (java.time.format.DateTimeParseException exception) { throw fail(400,"事件日期格式应为 yyyy-MM-dd"); }
        return data("type",type,"title",text(input,"title",2,80),"category",category,"description",text(input,"description",5,2000),"location",text(input,"location",2,100),"event_date",date,"contact",text(input,"contact",2,200),"hidden_features",text(input,"hidden_features",0,500),"updated_at",now());
    }
    private void images(Map<String,Object> input,long itemId,Map<String,Object> user) {
        Object values = input.getOrDefault("images",List.of());
        if (!(values instanceof List<?> list) || list.size()>3) throw fail(400,"每条信息最多三张图片");
        Set<Long> imageIds = new LinkedHashSet<>();
        for (Object value : list) {
            long attachmentId; try { attachmentId = Long.parseLong(value.toString()); } catch (Exception exception) { throw fail(400,"图片编号不正确"); }
            Map<String,Object> attachment = db.attachment(attachmentId);
            if (attachment == null || id(attachment,"owner_id") != id(user,"id") || !"PUBLIC".equals(attachment.get("kind"))) throw fail(403,"只能使用自己上传的公开图片");
            Long linked = db.imageItem(attachmentId); if (linked != null && linked != itemId) throw fail(409,"图片已经用于其他信息");
            imageIds.add(attachmentId);
        }
        db.unlinkImages(itemId); for (long attachmentId : imageIds) db.linkImage(itemId,attachmentId);
    }
    @Transactional public Map<String,Object> createItem(Map<String,Object> user,Map<String,Object> input) {
        Map<String,Object> item = itemInput(input); item.put("owner_id",user.get("id")); item.put("status","PENDING"); item.put("created_at",now());
        db.insertItem(item); images(input,id(item,"id"),user); audit(user,"发布","item",id(item,"id"),""); return detail(id(item,"id"),user);
    }
    @Transactional public Map<String,Object> editItem(Map<String,Object> user,long itemId,Map<String,Object> input) {
        Map<String,Object> previous = requireItem(itemId); requireOwner(user,previous);
        Map<String,Object> item = itemInput(input); item.put("id",itemId);
        if (db.editItem(item)!=1) throw fail(409,"已有申领历史或信息已结束，不能直接修改；请先处理相关流程");
        if (!admin(user) || id(user,"id")==id(previous,"owner_id")) images(input,itemId,user);
        notify(id(previous,"owner_id"),"信息《"+str(item,"title")+"》已修改，等待重新审核"); audit(user,"修改","item",itemId,""); return detail(itemId,user);
    }
    @Transactional public void deleteItem(Map<String,Object> user,long itemId) {
        Map<String,Object> item = requireItem(itemId); requireOwner(user,item);
        if (db.pendingCount(itemId)>0 || "HANDOVER".equals(item.get("status"))) throw fail(409,"请先结束申领或关闭信息");
        if (!admin(user) && db.claimCount(itemId)>0) throw fail(409,"存在申领历史，请使用关闭功能保留记录");
        db.deleteItem(itemId,now()); audit(user,"删除","item",itemId,"");
    }
    @Transactional public void review(Map<String,Object> user,long itemId,boolean approve,String reason) {
        requireAdmin(user); Map<String,Object> item = requireItem(itemId);
        if (!approve && reason.isBlank()) throw fail(400,"驳回时请填写原因");
        if (db.itemState(itemId,"PENDING",approve?"OPEN":"REJECTED",reason,now())!=1) throw fail(409,"仅可审核待审核信息");
        notify(id(item,"owner_id"),"《"+str(item,"title")+"》"+(approve?"审核通过":"被驳回："+reason)); audit(user,approve?"发布审核通过":"发布驳回","item",itemId,reason);
    }
    @Transactional public void close(Map<String,Object> user,long itemId,boolean resolved) {
        Map<String,Object> item = requireItem(itemId); requireOwner(user,item);
        if (resolved && (!"LOST".equals(item.get("type")) || !"OPEN".equals(item.get("status")))) throw fail(409,"仅寻找中的寻物启事可以标记已找回");
        if (Set.of("CLAIMED","RESOLVED","CLOSED").contains(str(item,"status"))) throw fail(409,"该信息已结束");
        if (!admin(user) && db.pendingCount(itemId)>0) throw fail(409,"存在进行中申领，请联系管理员处理");
        if (db.itemState(itemId,str(item,"status"),resolved?"RESOLVED":"CLOSED","",now())!=1) throw fail(409,"状态已变化，请刷新");
        for (Map<String,Object> claim : db.itemActiveClaims(itemId)) {
            db.claimState(id(claim,"id"),str(claim,"status"),"CANCELLED","物品已关闭",now()); notify(id(claim,"applicant_id"),"物品已关闭，相关申领已取消");
        }
        notify(id(item,"owner_id"),"《"+str(item,"title")+"》已"+(resolved?"找回":"关闭")); audit(user,resolved?"已找回":"关闭","item",itemId,"");
    }
    @Transactional public Map<String,Object> apply(Map<String,Object> user,long itemId,Map<String,Object> input) {
        Map<String,Object> item = requireItem(itemId);
        if (!visible(item,user) || !"FOUND".equals(item.get("type")) || !"OPEN".equals(item.get("status"))) throw fail(409,"该物品当前不接受申领");
        if (id(item,"owner_id")==id(user,"id")) throw fail(400,"不能申领自己发布的物品");
        long proofId = id(input,"proof_attachment_id");
        if (proofId>0) {
            Map<String,Object> proof = db.attachment(proofId);
            if (proof==null || id(proof,"owner_id")!=id(user,"id") || !"PROOF".equals(proof.get("kind"))) throw fail(403,"证明图片无效或不属于你");
        }
        Map<String,Object> claim = data("item_id",itemId,"applicant_id",user.get("id"),"proof",text(input,"proof",10,1500),"proof_attachment_id",proofId>0?proofId:null,"created_at",now(),"updated_at",now());
        db.insertClaim(claim); notify(id(user,"id"),"已提交《"+str(item,"title")+"》的申领，请等待审核"); audit(user,"提交申领","claim",id(claim,"id"),""); return db.claim(id(claim,"id"));
    }
    @Transactional public void withdraw(Map<String,Object> user,long claimId) {
        Map<String,Object> claim = requireClaim(claimId);
        if (id(claim,"applicant_id")!=id(user,"id")) throw fail(403,"只能撤回自己的申请");
        if (db.claimState(claimId,"PENDING","WITHDRAWN","用户撤回",now())!=1) throw fail(409,"仅待审核申请可以撤回");
        audit(user,"撤回申领","claim",claimId,"");
    }
    private Map<String,Object> requireClaim(long claimId) { Map<String,Object> claim = db.claim(claimId); if (claim==null) throw fail(404,"申领记录不存在"); return claim; }
    @Transactional public void claimAction(Map<String,Object> user,long claimId,String action,String reason) {
        requireAdmin(user); Map<String,Object> claim = requireClaim(claimId); long itemId = id(claim,"item_id");
        if (id(claim,"applicant_id")==id(user,"id")) throw fail(403,"不能审核或确认自己的申领");
        String previous; String next; String message;
        switch(action) {
            case "approve" -> {
                active(id(claim,"applicant_id")); active(id(requireItem(itemId),"owner_id")); previous="PENDING"; next="APPROVED"; message="审核通过，请按详情中的联系方式安排交接";
                if (db.itemState(itemId,"OPEN","HANDOVER","",now())!=1) throw fail(409,"已有其他申请进入交接或物品状态已变化");
            }
            case "reject" -> { if(reason.isBlank()) throw fail(400,"驳回请填写原因"); previous="PENDING"; next="REJECTED"; message="申领未通过："+reason; }
            case "cancel" -> {
                if(reason.isBlank()) throw fail(400,"取消交接请填写原因"); previous="APPROVED"; next="CANCELLED"; message="交接已取消："+reason;
                if(db.itemState(itemId,"HANDOVER","OPEN","",now())!=1) throw fail(409,"物品不处于交接中");
            }
            case "complete" -> {
                active(id(claim,"applicant_id")); previous="APPROVED"; next="COMPLETED"; message="交接完成，物品已标记领取";
                if(db.itemState(itemId,"HANDOVER","CLAIMED","",now())!=1) throw fail(409,"物品不处于交接中");
            }
            default -> throw fail(400,"不支持的申领操作");
        }
        if(db.claimState(claimId,previous,next,reason,now())!=1) throw fail(409,"申请状态已变化，请刷新");
        if(action.equals("complete")) for(Map<String,Object> other:db.itemActiveClaims(itemId)) {
            db.claimState(id(other,"id"),"PENDING","CANCELLED","物品已由其他申请人领取",now()); notify(id(other,"applicant_id"),"《"+str(claim,"title")+"》已由其他申请人领取，申请结束");
        }
        notify(id(claim,"applicant_id"),"《"+str(claim,"title")+"》："+message); notify(id(claim,"owner_id"),"《"+str(claim,"title")+"》申领进度："+message); audit(user,action,"claim",claimId,reason);
    }
    private void noOpenBusiness(long userId) { if(db.activeItems(userId)>0 || db.activeClaims(userId)>0) throw fail(409,"请先关闭未结束的发布、撤回申请或由管理员结束交接，再注销账号"); }
    @Transactional public void deleteAccount(Map<String,Object> user,String password) {
        if(admin(user)) throw fail(403,"管理员账号不能通过个人入口注销");
        if(!verify(password,str(user,"password_hash"))) throw fail(400,"密码不正确"); anonymize(user,id(user,"id"),"本人注销");
    }
    private void anonymize(Map<String,Object> actor,long userId,String reason) {
        noOpenBusiness(userId); if(db.anonymize(userId)!=1) throw fail(409,"账号不存在、已注销或不允许注销管理员"); db.hideOwnItems(userId); audit(actor,"注销账号","user",userId,reason);
    }
    @Transactional public void accountAction(Map<String,Object> user,long userId,String action,String reason) {
        requireAdmin(user); Map<String,Object> target = db.user(userId);
        if(target==null) throw fail(404,"账号不存在");
        if(!"USER".equals(target.get("role")) || "DELETED".equals(target.get("status"))) throw fail(403,"只能管理尚未注销的普通用户账号");
        if(reason.isBlank()) throw fail(400,"请填写账号处理原因");
        if(action.equals("delete")) { anonymize(user,userId,reason); return; }
        String status = switch(action) { case "ban" -> "BANNED"; case "unlock" -> "ACTIVE"; default -> throw fail(400,"操作不支持"); };
        db.userStatus(userId,status,reason); notify(userId,"账号处理："+(status.equals("ACTIVE")?"已解锁":"已封禁")+"；原因："+reason); audit(user,action,"user",userId,reason);
    }
    public void audit(Map<String,Object> user,String action,String type,long target,String reason) { db.audit(id(user,"id"),action,type,target,reason,now()); }
    private void notify(long userId,String message) { db.notify(userId,message,now()); }
}
